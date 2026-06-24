# Thiết kế Bảo mật (Security Design) - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Final (W11 T6 Pack #1) -> Updated (W12 T4 Pack #2)
-->

## 1. Network Security

### 1.1 Network Diagram

CDO platform áp dụng nguyên tắc cô lập chặt chẽ bên trong một VPC chuyên biệt. Tất cả các tài nguyên compute đều chạy trong các private subnets không có route đi ra internet gateway. Mọi luồng giao tiếp với AWS API đều được định tuyến nội bộ qua AWS VPC Endpoints.

Thiết kế bảo mật giả định hai ranh giới tin cậy chính: ranh giới tài khoản quản trị CDO và ranh giới tài khoản thành viên. Dữ liệu chi phí, payload quyết định của AI, payload cảnh báo và bản ghi kiểm toán containment đều nằm trong đường dẫn mạng AWS do CDO kiểm soát. Bộ điều phối Step Functions gọi trực tiếp hàm AI Engine Request Lambda. Mô hình hàng đợi bất đồng bộ sử dụng SQS/DLQ tách biệt khối lượng công việc suy luận nặng khỏi việc xác thực yêu cầu. Request Lambda xử lý các yêu cầu phát hiện đầu vào, đẩy chúng vào hàng đợi SQS và trả về trạng thái ngay lập tức. Lưu ý rằng `/v1/detect` và `/v1/detect/result/{audit_id}` đại diện cho ngữ nghĩa hợp đồng logic để tích hợp mô hình, chứ không phải các tuyến đường REST/HTTP được triển khai, vì không có Private API Gateway nào được triển khai. AI Engine không nhận thông tin xác thực trực tiếp để thực hiện hành động containment trên tài khoản thành viên.

```mermaid
graph TD
    subgraph "CDO Management Account VPC (ap-southeast-1)"
        subgraph "Private Subnets (Serverless Compute & Queue)"
            AILambdaReq[AI Engine Request Lambda]
            AILambdaWorker[AI Engine Worker Lambda]
            SQSQueue[SQS Ingest Queue]
            L_Pull[Ingestion Lambda]
            L_Cont[Containment Lambda]
        end

        subgraph "VPC Endpoint Subnet"
            VPCE[VPC Endpoints: S3, DDB, Secrets Mgr, ECR, KMS, Logs, STS, Lambda]
        end
    end

    subgraph "External Cloud Environment"
        S3Raw[(S3 Raw Zone)]
        S3Cur[(S3 Curated Zone)]
        DDB[(DynamoDB Run State & Results)]
        SM[Secrets Manager]
    end

    %% Network flows
    L_Pull -->|VPC Endpoint HTTPS| VPCE
    VPCE -->|Private link| S3Raw
    L_Cont -->|VPC Endpoint HTTPS| VPCE
    VPCE -->|Private link| DDB
    
    %% Serverless traffic
    AILambdaReq -->|Enqueue| SQSQueue
    SQSQueue -->|Trigger| AILambdaWorker
    AILambdaReq -->|Fetch secrets via SDK| VPCE
    AILambdaWorker -->|Fetch secrets via SDK| VPCE
    VPCE -->|Private link| SM
```

*Chú thích: Các hàm AI Engine Request và Worker Lambda, cùng các hàm Lambda điều phối và adapter dữ liệu, được triển khai trong các subnets chỉ có quyền private. Các thành phần này sử dụng các AWS VPC Interface Endpoints (PrivateLink) riêng biệt để kết nối tới các dịch vụ AWS, ngăn chặn mọi luồng truyền tải dữ liệu qua mạng internet công cộng. Không có Private API Gateway nào được triển khai; Step Functions gọi trực tiếp hàm Request Lambda và việc thực thi Worker được dẫn dắt bất đồng bộ qua SQS.*

### 1.2 Security Groups

Luồng traffic giữa các thành phần compute được kiểm soát thông qua các stateful security groups tuân thủ nguyên tắc đặc quyền tối thiểu:

| SG name | Inbound | Outbound | Attached to |
|---|---|---|---|
| `lambda-sg` | None (Gọi trực tiếp qua dịch vụ thực thi programmatic) | TCP 443 (đến `vpce-sg`) | Các hàm Lambda Ingestion, Containment, và AI Engine Request & Worker |
| `vpce-sg` | TCP 443 (từ `lambda-sg`) | None | VPC endpoints (S3, DynamoDB, ECR, Secrets Mgr, KMS, Logs, STS, Lambda) |

### 1.3 Network ACL / VPC Endpoint

Các VPC interface endpoints được cấu hình bật tính năng Private DNS, định tuyến toàn bộ traffic đến:
- `com.amazonaws.ap-southeast-1.s3` (Gateway Endpoint)
- `com.amazonaws.ap-southeast-1.dynamodb` (Gateway Endpoint)
- `com.amazonaws.ap-southeast-1.secretsmanager` (Interface Endpoint)
- `com.amazonaws.ap-southeast-1.ecr.api` (Interface Endpoint)
- `com.amazonaws.ap-southeast-1.ecr.dkr` (Interface Endpoint)
- `com.amazonaws.ap-southeast-1.logs` (Interface Endpoint - CloudWatch logs)
- `com.amazonaws.ap-southeast-1.kms` (Interface Endpoint - Key Management Service)
- `com.amazonaws.ap-southeast-1.sts` (Interface Endpoint - Security Token Service)
- `com.amazonaws.ap-southeast-1.lambda` (Interface Endpoint - Lambda execution)

Security groups và IAM resource policies được triển khai để giới hạn kết nối (ví dụ: Request Lambda chỉ chấp nhận hành động gọi được bắt đầu bởi vai trò Step Functions, và chính sách SQS Queue chỉ cho phép xuất bản tin nhắn từ vai trò của Request Lambda).

Các chính sách endpoint được thu hẹp phạm vi vào tập hợp hành động thực tế nhỏ nhất. S3 gateway endpoint cho phép đọc từ các tiền tố xuất CUR đã phê duyệt và chỉ ghi vào các bucket raw/curated của CDO. DynamoDB endpoint chỉ cho phép truy cập vào các bảng run-state, idempotency, kiểm toán và bảng materialized hiển thị của dashboard. Các interface endpoint dành cho Secrets Manager, ECR và CloudWatch Logs bị giới hạn trong các security group của VPC CDO và các role thực thi. Các Network ACL duy trì tính đơn giản và không trạng thái (stateless), với lượt truy cập công cộng bị từ chối và lưu lượng phản hồi tạm thời chỉ được phép trong phạm vi private subnet.

## 2. IAM & Access Control

### 2.1 Service Roles

Các IAM service roles trong AWS thực thi sự phân tách trách nhiệm nghiêm ngặt. Đặc biệt, không có service role nào có quyền admin hoặc quyền thực hiện các tác vụ phá hủy trên môi trường production:

| Role | Used by | Permissions |
|---|---|---|
| `FinOpsStepFunctionsRole` | Step Functions | `states:StartExecution`, `states:DescribeExecution`, `lambda:InvokeFunction` |
| `FinOpsCURPullerRole` | `LambdaCURPuller` | `s3:GetObject` (trên CUR S3 bucket của tài khoản đích), `s3:PutObject` (trên raw S3 bucket), `ce:GetCostAndUsage` |
| `FinOpsAiRequestExecutionRole` | AI Engine Request Lambda | `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`, `secretsmanager:GetSecretValue` (qua SDK), `sqs:SendMessage` (để xếp hàng các yêu cầu detect), `dynamodb:GetItem` / `dynamodb:Query` (để lấy trạng thái kết quả) |
| `FinOpsAiWorkerExecutionRole` | AI Engine Worker Lambda | `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`, `secretsmanager:GetSecretValue` (qua SDK), `sqs:ReceiveMessage` / `sqs:DeleteMessage` (để thăm dò hàng đợi), `s3:GetObject` / `s3:PutObject` (đọc dữ liệu chi phí và ghi checkpoint/features), `dynamodb:PutItem` (để lưu trữ kết quả suy luận) |
| `FinOpsContainmentRole` | `LambdaContainment` | `ec2:CreateTags` (non-prod), `asg:UpdateAutoScalingGroup` (non-prod). Cấu hình explicit deny cho các quyền `iam:*`, `s3:Delete*`, và xóa tài nguyên prod. |

> [!IMPORTANT]
> **Ranh giới Bảo mật Cứng**: Mọi role thực thi của CDO đều đi kèm một Service Control Policy (SCP) để đảm bảo hệ thống **NEVER terminate prod, delete data, hoặc modify IAM**. Các tác vụ containment trên production chỉ giới hạn ở mức tag, suggest, hoặc dry-run kiểm toán.

### 2.2 Lambda Execution Roles

Các hàm AWS Lambda sử dụng các Role thực thi (Execution Roles) để áp dụng nguyên tắc đặc quyền tối thiểu:
1. **Lambda Execution Role** (`FinOpsAiRequestExecutionRole`, `FinOpsAiWorkerExecutionRole`): Được dịch vụ Lambda sử dụng để chạy mã hàm, kéo hình ảnh container từ ECR và ghi log thực thi vào CloudWatch.
2. **Cô lập quyền truy cập**: Mã ứng dụng chạy bên trong các hàm Lambda sử dụng các role này để truy vấn Secrets Manager (qua SDK), đọc/ghi vào dữ liệu chi phí curated trong S3, thăm dò từ hàng đợi SQS, hoặc ghi kết quả vào DynamoDB. Đội ngũ CDO sở hữu các role thực thi này như một phần của nền tảng host, trong khi đội AIOps cung cấp các container image được gắn phiên bản.

Workloads không kế thừa quyền từ host. Mỗi hàm Lambda được liên kết rõ ràng với role thực thi tương ứng trong cấu hình hàm.

- **Lambda Function Role Mappings**:

| Tên Hàm | IAM Execution Role | Managed Policies / Custom Scoped Policies |
|---|---|---|
| AI Engine Request Lambda | `FinOpsAiRequestExecutionRole` | Quyền đọc Secrets Manager (contract và API keys), SQS gửi tin nhắn, DynamoDB truy vấn trạng thái chạy, CloudWatch Logs ghi log. |
| AI Engine Worker Lambda | `FinOpsAiWorkerExecutionRole` | Quyền đọc-ghi S3 (cost files & checkpoints), SQS thăm dò tin nhắn, DynamoDB ghi kết quả, CloudWatch Logs ghi log. |

### 2.3 Cross-account Access

Quyền truy cập chéo tài khoản (cross-account) tới các CUR buckets của tài khoản thành viên được quản lý bởi S3 bucket policies tại tài khoản đích, cho phép quyền đọc đối với `FinOpsCURPullerRole` tập trung thông qua External IDs.
Các hành động containment tại các tài khoản thành viên được kích hoạt thông qua cơ chế Assume IAM Role chéo tài khoản (`AssumeRole`). Role `LambdaContainment` tại tài khoản quản trị (management account) sẽ assume role `FinOpsContainmentWorkerRole` tại tài khoản đích, thực hiện gắn thẻ tag hoặc scale down các sandbox ASGs.

Mỗi chính sách tin cậy role chéo tài khoản đều bao gồm một ID bên ngoài (external ID), điều kiện tài khoản nguồn và yêu cầu gắn thẻ session để nhật ký kiểm toán có thể ánh xạ từng hành động trở lại lượt chạy CDO. Các role trên production bao gồm các lệnh deny rõ ràng đối với việc chấm dứt tài nguyên, các hoạt động lưu trữ mang tính phá hủy và đột biến IAM. Các role trên non-production có thể cho phép các hành động containment hạn chế chỉ khi yêu cầu đi vào bao gồm một `execution_mode` được phê duyệt, tag môi trường, ID bất thường và ID quyết định chính sách. Nếu bất kỳ trường nào trong số đó bị thiếu, containment worker sẽ ghi lại sự kiện kiểm toán bị từ chối và thoát ra mà không thử lại.

### 2.4 Xác thực & Ủy quyền Bảng điều khiển (Cognito)

Kiểm soát truy cập cho Bảng điều khiển Tài chính tĩnh S3 + CloudFront được thực thi thông qua tích hợp với Amazon Cognito và ủy quyền viewer-request của Lambda@Edge:
- **Bảo vệ OAC của CloudFront**: Bucket S3 chứa các tài nguyên bảng điều khiển hoàn toàn riêng tư. Truy cập công cộng trực tiếp bị chặn bằng Origin Access Control (OAC). Đường dẫn truy cập duy nhất là qua phân phối CloudFront, nơi thực thi xác thực.
- **Hosted UI Code Flow**: Người dùng truy cập các endpoint Hosted UI qua các redirect của CloudFront. Quá trình xác thực được xử lý bằng Authorization Code Flow với PKCE. Cognito cấp các mã JWT token (ID, Access, và Refresh) sau khi đăng nhập thành công.
- **Lưu trữ Token an toàn**: Ứng dụng trao đổi authorization code lấy token, lưu trữ chúng dưới dạng secure cookies (các cờ `Secure`, `HttpOnly`, `SameSite=Strict`) với vòng đời phiên ngắn 1 giờ.
- **Xác thực Token bằng Lambda@Edge**: Hàm Lambda@Edge viewer-request của CloudFront chặn mọi yêu cầu, phân tách JWT cookie, kiểm tra chữ ký đối với endpoint JWKS của Cognito và xác thực các claim (hết hạn, audience, issuer). Token không hợp lệ hoặc hết hạn sẽ kích hoạt tự động redirect về trang đăng nhập Hosted UI.
- **Chính sách truy cập theo nhóm (Group-Based Access Policies)**:
  - `finops-finance-readonly`: Thành viên được ủy quyền xem trực quan xu hướng chi tiêu, tóm tắt bất thường và các bản ghi lịch sử kiểm toán. Giao diện UI chặn hiển thị các lệnh CLI, rollback script thô hoặc các nút kích hoạt thực thi containment.
  - `finops-engineering-operator`: Thành viên được ủy quyền truy cập chi tiết kỹ thuật, xem các lệnh thực thi `rollback_script_encapsulated` thô, và kích hoạt các hành động programmatic được phê duyệt để gia hạn (đại diện cho ngữ nghĩa `/v1/action/extend`) và rollback (đại diện cho ngữ nghĩa `/v1/action/rollback`).
  - `finops-cdo-admin`: Thành viên được cấp quyền quản lý chính sách truy cập, điều chỉnh phân bổ người dùng vào nhóm và cấu hình các cờ kiểm soát nền tảng toàn cục.

## 3. Secrets Management

### 3.1 Secrets Inventory

Các secret sau đây được lưu trữ trong AWS Secrets Manager:

| Secret | Nơi lưu trữ | Chu kỳ xoay vòng | Được truy cập bởi |
|---|---|---|---|
| `finops/ai-engine/api-key` | AWS Secrets Manager (mã hóa bằng KMS CMK) | Tự động mỗi 30 ngày | AI Engine Request Lambda (qua SDK khi khởi động lạnh) |
| `finops/dashboard/db-creds` | AWS Secrets Manager | Tự động mỗi 60 ngày | Athena crawler / QuickSight dataset engine trong tương lai |
| `finops/alerting/slack-webhook` | AWS Secrets Manager | Thủ công mỗi 90 ngày | `LambdaAlertRouting` |
| `finops/ai-engine/contract-signing-key` | AWS Secrets Manager | Tự động mỗi 90 ngày | Hàm Lambda xác thực của Step Functions và AI Engine Request Lambda |
| `finops/containment/external-id-seed` | AWS Secrets Manager | Xoay vòng thủ công khi xảy ra sự cố | Quy trình cung cấp vai trò containment |

### 3.2 Inject Pattern

Chúng tôi sử dụng SDK AWS Secrets Manager để lấy các secret trong các hàm Lambda khi runtime, thay vì truyền chúng dưới dạng các biến môi trường plaintext. Secrets được phân giải trong quá trình function cold-start, cache trong ngữ cảnh thực thi toàn cục của hàm, và được kiểm tra hợp lệ theo các chính sách TTL cache (ví dụ: 5 phút) để tránh gọi API trực tiếp quá nhiều ở các yêu cầu tiếp theo.

Ví dụ, hàm container Lambda truy xuất API key của nó một cách động bằng SDK AWS:
```python
import boto3
import os

def get_api_key():
    secret_name = os.environ["API_KEY_SECRET_ARN"]
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_name)
    return response["SecretString"]
```

Đường dẫn inject sử dụng truy xuất an toàn khi runtime. Các hàm Lambda đọc trực tiếp secrets thông qua Secrets Manager SDK vì chúng là các tác vụ container ngắn hạn. Terraform tạo các secret container và quyền IAM, nhưng nó không lưu trữ giá trị bí mật trong `.tfvars`, Terraform state, hay các cấu hình build.

### 3.3 Anti-leak Controls

- **CI/CD Scanning**: Gitleaks được tích hợp vào pipeline GitHub Actions, chặn merge các PR nếu phát hiện các thông tin xác thực ở dạng plain-text hoặc các API key.
- **VPC Endpoint Restriction**: Các chính sách (policies) trên Secrets Manager VPC Endpoints giới hạn quyền truy cập chỉ cho phép từ dải mạng CIDR của VPC quản trị CDO.
- **Log Redaction**: Toàn bộ nhật ký hoạt động đầu ra của ứng dụng được chạy qua bộ lọc regex để che giấu các thông tin nhạy cảm, thay thế các API keys, tokens, và các header authorization bằng nhãn `[REDACTED]`.
- **Kiểm soát state của Terraform (Terraform State Control)**: State của Terraform được mã hóa, kiểm soát quyền truy cập và được xem xét kỹ lưỡng để các giá trị nhạy cảm được mô hình hóa dưới dạng tham chiếu bí mật (secret reference) thay vị đầu ra văn bản thuần túy.
- **Ranh giới container (Container Boundary)**: Workloads Lambda chạy bên trong các môi trường thực thi an toàn dưới danh nghĩa người dùng non-root, mount bộ nhớ tạm `/tmp` (được mã hóa) dưới dạng chỉ đọc theo mặc định ngoại trừ các thư mục nháp tạm thời, và tránh ghi tài liệu bí mật vào các persistent volume.
- **Phản ứng sự cố (Incident Response)**: Nghi ngờ lộ bí mật sẽ kích hoạt xoay vòng bí mật, xem lại lịch sử Git, tra cứu CloudTrail cho `GetSecretValue` và tạm dừng các thông tin xác thực triển khai bị ảnh hưởng.

## 4. Encryption

### 4.1 At Rest

Toàn bộ dữ liệu của hệ thống được mã hóa tại chỗ (at rest) sử dụng Customer Managed Keys (CMKs) trong dịch vụ AWS KMS:

| Dữ liệu (Data) | Nơi lưu trữ (Storage) | KMS key | Ghi chú |
|---|---|---|---|
| Dữ liệu chi phí Raw/Curated | S3 | `aws/s3` hoặc CMK tùy chỉnh | Bật tính năng S3 Bucket Key để giảm thiểu chi phí gọi KMS API. |
| Run State & Metadata | DynamoDB | `aws/dynamodb` hoặc CMK tùy chỉnh | Mã hóa sử dụng KMS. |
| Secrets Store | Secrets Manager | `finops-secrets-key` | Việc giải mã yêu cầu chính sách role trust rõ ràng. |
| Lưu trữ tạm thời / Container Lambda | Bộ lưu trữ Lambda | `aws/lambda` hoặc CMK tùy chỉnh | Toàn bộ dung lượng lưu trữ tạm thời của hàm (bao gồm /tmp lên đến 10 GB) được mã hóa mặc định. |
| Nhật ký kiểm toán (Audit Logs) | S3 Object Lock | `finops-audit-key` | Lưu trữ tối thiểu 90 ngày với compliance lock. |

### 4.2 In Transit

- **Yêu cầu TLS**: Tất cả traffic đi vào và đi ra đều yêu cầu mã hóa TLS 1.3 (với TLS 1.2 là phiên bản tối thiểu được chấp nhận).
- **Traffic nội bộ**: Giao tiếp function-to-function và tin nhắn SQS được mã hóa hoàn toàn khi truyền tải natively bởi các dịch vụ AWS sử dụng TLS.
- **Các cuộc gọi AI Engine**: Step Functions gọi trực tiếp hàm AI Engine Request Lambda nội bộ qua mạng riêng tư VPC. Payload yêu cầu bao gồm một phiên bản hợp đồng và ID tương quan, và payload sẽ được xác thực bên trong môi trường thực thi của hàm.
- **Alert Webhook**: Tích hợp Slack hoặc email được gọi từ Lambda cảnh báo sau khi giảm thiểu payload. Dữ liệu chi phí nhạy cảm được liên kết thông qua các tham chiếu dashboard/audit nội bộ thay vì được nhúng trực tiếp vào các tin nhắn bên ngoài.

### 4.3 Key Management

- **Chu kỳ xoay vòng (Rotation)**: Các khóa CMK tự động xoay vòng mỗi 365 ngày.
- **Access Policies**: Các key policies thực thi phân tách nhiệm vụ, đảm bảo chỉ có các pipeline CI/CD mới có quyền thay đổi cấu hình key, và chỉ có các role thực thi (Lambda container và các hàm nền tảng) mới có quyền gọi các hàm giải mã (decrypt).
- **Kiểm toán (Audit)**: Toàn bộ lịch sử sử dụng key được theo dõi và ghi lại qua AWS CloudTrail.
- **Kiểm soát bán kính ảnh hưởng (Blast-radius control)**: Ưu tiên sử dụng các KMS CMK riêng biệt cho dữ liệu chi phí, hồ sơ kiểm toán, secrets và bộ nhớ tạm thời của Lambda, trừ khi bộ phận Finance và Security phê duyệt hợp nhất vì lý do chi phí.
- **Truy cập Break-glass**: Quyền giải mã thủ công không được cấp cho các nhà phát triển hàng ngày. Truy cập tạm thời yêu cầu phê duyệt sự cố, tham chiếu ticket, thời gian hết hạn và xem xét sau khi sử dụng.

## 5. Audit Logging

### 5.1 What to Log

Mọi hành động kiểm soát do CDO platform thực hiện đều được ghi chép lại. Đối với các hành động containment, schema log sau sẽ được lưu trữ vào cơ sở dữ liệu và S3:
```json
{
  "actor": "cdo-platform-orchestrator",
  "timestamp": "2026-06-23T07:20:00Z",
  "correlation_id": "corr-uuid-4444-5555-6666",
  "idempotency_key": "123456789012:2026-06-22T00:00:00Z",
  "anomaly_id": "anom-9988-7766",
  "resource_owner": "squad-prediction-models",
  "resource_id": "arn:aws:ec2:ap-southeast-1:123456789012:instance/i-0abcdef123456",
  "before_state": {
    "instance_type": "g5.4xlarge",
    "status": "running",
    "tags": {
      "Environment": "sandbox"
    }
  },
  "proposed_after_state": {
    "tags": {
      "Environment": "sandbox",
      "FinOpsWatch": "ReviewRequired",
      "AnomalyDetected": "true"
    }
  },
  "execution_mode": "dry-run",
  "rollback_path": {
    "action": "remove_tags",
    "keys": ["FinOpsWatch", "AnomalyDetected"]
  },
  "approval_status": "pending_squad_response",
  "retention_location": "s3://cdo-audit-trail-bucket/audit/year=2026/month=06/",
  "retention_period_days": 90,
  "audit_chain": {
    "audit_id": "8f3b610c-18a4-4e2b-9801-bde901844b20",
    "event_hash": "673f8a0dc...",
    "previous_hash": "a4f891b0d..."
  }
}
```

Bản ghi kiểm toán được ghi lại trước khi thực hiện bất kỳ hoạt động apply nào và được cập nhật sau hoạt động đó với trạng thái cuối cùng. Mọi bản ghi hành động containment đều được liên kết mã hóa với bản ghi trước đó trong một chuỗi append-only lưu trữ tại DynamoDB và S3, với mã băm kiểm tra toàn vẹn được tính toán là `sha256(current_payload + previous_hash)` nhằm đảm bảo khả năng chống giả mạo (tamper-evident). Hoạt động dry-run vẫn tạo ra các bản ghi kiểm toán vì Finance cần xem nền tảng sẽ làm gì và tại sao hành động đó vẫn an toàn. Bộ dữ liệu huấn luyện mô hình AI không được CDO ghi nhật ký; CDO chỉ ghi nhật ký metadata cuộc gọi, các trường quyết định được trả về và các tham chiếu bằng chứng vận hành cần thiết cho việc cảnh báo và containment. Telemetry gửi tới AI Engine để phát hiện bất thường là dữ liệu chi phí CUR-only và tuyệt đối không bao gồm các tín hiệu hiệu năng CloudWatch. Hệ thống log và metrics của CloudWatch chỉ phục vụ cho việc giám sát vận hành của CDO và cảnh báo SRE. Mọi hoạt động xác thực bảng điều khiển (đăng nhập thành công, đăng xuất, làm mới phiên hết hạn), lỗi xác thực (đăng nhập thất bại, chữ ký token không hợp lệ, vi phạm cửa sổ replay) và các nỗ lực truy cập nhóm không được ủy quyền (như người dùng Finance readonly cố gắng gọi một hành động của operator) đều được ghi nhật ký ngay lập tức vào CloudWatch Logs và truyền về S3 để lưu giữ lịch sử kiểm toán.

### 5.2 Storage + Retention

Nhật ký kiểm toán được lưu trữ bảo mật với các cấu hình chống ghi đè:

| Loại Log (Log type) | Nơi lưu trữ | Retention | Giao diện truy vấn |
|---|---|---|---|
| Containment Audits | S3 + Object Lock | Tối thiểu 90 ngày | Athena / DynamoDB |
| AWS API Calls | CloudTrail (S3 Raw) | 1 năm | Athena |
| AI Engine Lambda Logs | CloudWatch Logs | 30 ngày | CloudWatch Logs Insights |
| App/Lambda Logs | CloudWatch Logs | 14 ngày | CloudWatch Logs Insights |

Kho lưu trữ kiểm toán containment được thiết kế dưới dạng append-only. DynamoDB hỗ trợ tra cứu dashboard với độ trễ thấp, trong khi S3 với Object Lock là kho lưu trữ bằng chứng bền vững. Bảng điều khiển nên liên kết đến ID bản ghi kiểm toán thay vì sao chép trạng thái trước/sau nhạy cảm trong các tin nhắn cảnh báo. Thời gian lưu giữ ngắn hơn 90 ngày không được phép đối với các bản ghi containment, ngay cả trong sandbox, vì yêu cầu của capstone đo lường khả năng truy vết của các quyết định tự động.

### 5.3 Synthetic Data Handling

Để tránh trộn lẫn dữ liệu hóa đơn tổng hợp (synthetic logs) với các cấu hình thực tế trong quá trình kiểm thử:
- Các lệnh inject demo do CDO sở hữu được đánh dấu với `source = "synthetic-demo"`.
- Bộ lọc trên dashboard (giao diện S3 + CloudFront) cho phép bật/tắt giữa hiển thị dữ liệu thực tế và dữ liệu giả lập.
- Các hành động containment giả lập được định tuyến đến một mock endpoint, giữ nguyên tài nguyên AWS thực tế không bị ảnh hưởng.
- Các bộ dữ liệu huấn luyện, cải tiến và backtest mô hình do AIOps sở hữu nằm ngoài quyền sở hữu của CDO. CDO có thể lưu trữ các chỉ số mô hình do AIOps cung cấp làm bằng chứng tích hợp, nhưng không sao chép hoặc phân loại lại dữ liệu huấn luyện của đội AI thành dữ liệu vận hành của CDO.

## 6. CI Security Controls

- **Chạy quyền Non-Root**: Cấu hình container bắt buộc chạy ứng dụng dưới quyền user non-root (ví dụ: chạy dưới user `1000` in Dockerfile).
- **Cô Lập Hàm Lambda**: Các hàm Lambda container chạy trong các môi trường sandbox độc lập, chỉ đọc (ngoại trừ thư mục `/tmp`) và thực thi với các đặc quyền tối thiểu bằng các execution role riêng biệt.
- **Giới Hạn Tài Nguyên**: Các giới hạn concurrency (Reserved Concurrency) được cấu hình trên các hàm Lambda để ngăn chặn các cuộc tấn công từ chối dịch vụ hoặc cạn kiệt tài nguyên của tài khoản.

## 7. Compliance Touchpoints

| Standard | Relevant controls (capstone scope) |
|---|---|
| **SOC 2 Type II** | Least privilege IAM roles, VPC private network boundaries, Secrets Manager rotation, encrypted S3 buckets. |
| **ISO 27001** | Báo cáo rà soát truy cập hàng tuần, nhật ký containment không thể sửa đổi, tự động xoay KMS key. |
| **HIPAA** | Ngoài phạm vi (Dữ liệu hóa đơn chi phí không chứa Thông tin sức khỏe được bảo vệ). |

Ánh xạ tuân thủ cố ý được giới hạn ở các kiểm soát liên quan đến capstone. Nền tảng xử lý siêu dữ liệu thanh toán và vận hành, không phải payload ứng dụng của khách hàng, nhưng dữ liệu vẫn tiết lộ cấu trúc tài khoản, mức độ sử dụng tài nguyên và các thẻ tag của chủ sở hữu. Điều đó làm cho đặc quyền tối thiểu, thời gian lưu giữ kiểm toán, mã hóa và giảm thiểu cảnh báo trở thành bắt buộc ngay cả khi không có dữ liệu khách hàng được quy định.

## 8. Open Questions

- [ ] **Cross-Account KMS Strategy**: Nên sử dụng KMS key tập trung với chính sách chia sẻ chéo tài khoản, hay sử dụng KMS key cục bộ tại mỗi tài khoản đích để mã hóa S3 CUR bucket?
- [ ] **Operator Notification Channels**: Khi một hành động containment bị từ chối, hệ thống nên gửi cảnh báo qua PagerDuty hay gửi trực tiếp về kênh Slack của đội bảo mật?
- [ ] **External Alert Redaction**: Che giấu cảnh báo bên ngoài: Những trường chi phí nào được phép hiển thị trong Slack/email và những trường nào bắt buộc phải giữ riêng tư chỉ trên dashboard?
- [ ] **Break-glass Approver**: Người phê duyệt khẩn cấp: Ai sẽ phê duyệt quyền giải mã tạm thời hoặc truy cập điều tra production trong quá trình xảy ra sự cố?

## Related documents

- [`02_infra_design_vi.md`](02_infra_design_vi.md) - Thiết kế hạ tầng, bố cục VPC và tích hợp tính toán serverless.
- [`04_deployment_design_vi.md`](04_deployment_design_vi.md) - Pipeline CI/CD, các pipeline triển khai GitHub Actions, và chu kỳ xoay Secrets.
