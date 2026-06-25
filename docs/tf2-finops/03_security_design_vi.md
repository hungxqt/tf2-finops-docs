# Thiết kế Bảo mật (Security Design) - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Final (W11 T6 Pack #1) -> Updated (W12 T4 Pack #2)
-->

## 1. Network Security

### 1.1 Network Diagram

CDO platform áp dụng nguyên tắc cô lập chặt chẽ bên trong một VPC chuyên biệt. Tất cả các tài nguyên compute đều chạy trong các private subnets không có route đi ra internet gateway. Mọi luồng giao tiếp với AWS API đều được định tuyến nội bộ qua AWS VPC Endpoints.

Thiết kế bảo mật giả định hai ranh giới tin cậy chính: ranh giới tài khoản quản trị CDO và ranh giới tài khoản thành viên. Dữ liệu chi phí, payload quyết định của AI, payload cảnh báo và bản ghi kiểm toán containment đều nằm trong đường dẫn mạng AWS do CDO kiểm soát. Bộ điều phối Step Functions tương tác với hàm AI Engine Lambda (chạy trong môi trường thực thi container riêng tư) thông qua Application Load Balancer (ALB) nội bộ riêng tư hoặc HTTPS adapter tương đương sử dụng chữ ký AWS SigV4. Các endpoint riêng tư `/v1/detect`, `/v1/decide`, `/v1/verify`, `/v1/status/{id}`, `/v1/audit/{audit_id}/rollback`, và `/health` được hiển thị đầy đủ thông qua đích compute ALB riêng tư an toàn này. AI Engine không nhận thông tin xác thực trực tiếp để thực hiện hành động containment trên tài khoản thành viên. SQS/DLQ chỉ được sử dụng cho hàng đợi retry của alert routing chứ không nằm trong luồng phát hiện.

```mermaid
graph TD
    subgraph "CDO Management Account VPC (ap-southeast-1)"
        subgraph "Private Subnets (Serverless Compute)"
            L_Pull[Ingestion Lambda]
            L_Cont[Containment Lambda]
            L_Alert[Alert Routing Lambda]
            SQSQueue[SQS Alert Queue]
            ALB[Private Internal ALB / HTTPS Adapter]
            AILambda[AI Engine Lambda Function]
        end

        subgraph "VPC Endpoint Subnet"
            VPCE[VPC Endpoints: S3, DynamoDB, ECR, KMS, Logs, STS, Secrets]
        end
    end

    subgraph "External Storage & Services"
        S3Raw[(S3 Raw Zone)]
        S3Cur[(S3 Curated Zone)]
        S3Audit[(S3 Authoritative Audit Store)]
        DDB_Idemp[(DynamoDB finops-idempotency-{env})]
        DDB_Rollback[(DynamoDB finops-rollback-cache)]
        DDB_Dash[(DynamoDB Dashboard Cache)]
        SM[Secrets Manager]
    end

    %% Network flows
    L_Pull -->|VPC Endpoint HTTPS| VPCE
    VPCE -->|Private link| S3Raw
    VPCE -->|Private link| S3Cur
    L_Pull -->|HTTPS SigV4| ALB
    ALB -->|Forward API request| AILambda
    L_Cont -->|VPC Endpoint HTTPS| VPCE
    VPCE -->|Private link| S3Audit
    L_Alert -->|Enqueue retry| SQSQueue
    
    %% Serverless traffic
    AILambda -->|Fetch secrets via SDK| VPCE
    VPCE -->|Private link| SM
    AILambda -->|Read curated data| VPCE
    VPCE -->|Private link| S3Cur
```

*Chú thích: Hàm AI Engine Lambda, Application Load Balancer (ALB), và các tác vụ compute nền tảng khác chạy trong các subnets chỉ có quyền private. Các thành phần này sử dụng các AWS VPC Interface/Gateway Endpoints (PrivateLink) riêng biệt để kết nối tới các dịch vụ AWS một cách riêng tư. Step Functions và compute nền tảng truy cập AI Engine thông qua ALB nội bộ bằng HTTPS và xác thực AWS SigV4. SQS/DLQ chỉ được sử dụng cho hàng đợi retry của alert routing chứ không nằm trong luồng phát hiện.*

### 1.2 Security Groups

Luồng traffic giữa các thành phần compute được kiểm soát thông qua các stateful security groups tuân thủ nguyên tắc đặc quyền tối thiểu:

| SG name | Inbound | Outbound | Attached to |
|---|---|---|---|
| `alb-sg` | TCP 443 (từ orchestration/compute) | TCP 8080 (đến `lambda-sg`) | Private Internal ALB / HTTPS Adapter |
| `lambda-sg` | TCP 8080 (chỉ từ `alb-sg`, cho AI Engine Lambda) | TCP 443 (đến `vpce-sg`) | Các hàm Lambda Ingestion, Containment, Alert Routing, và AI Engine Lambda |
| `vpce-sg` | TCP 443 (từ `lambda-sg`) | None | VPC endpoints (S3, DynamoDB, ECR, Secrets Mgr, KMS, Logs, STS) |

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

Security groups và IAM resource policies được triển khai để giới hạn kết nối (ví dụ: AI Engine Lambda chỉ chấp nhận hành động gọi được bắt đầu bởi vai trò Step Functions, và chính sách SQS Alert Queue chỉ cho phép xuất bản tin nhắn từ vai trò của Alert Routing Lambda).

Các chính sách endpoint được thu hẹp phạm vi vào tập hợp hành động thực tế nhỏ nhất. S3 gateway endpoint cho phép đọc từ các tiền tố xuất CUR đã phê duyệt, chỉ ghi vào các bucket raw/curated của CDO và đọc/ghi vào `s3_audit_bucket` có Object Lock. DynamoDB endpoint chỉ cho phép truy cập vào bảng materialized hiển thị (read cache) của dashboard. Các interface endpoint dành cho Secrets Manager, ECR và CloudWatch Logs bị giới hạn trong các security group của VPC CDO và các role thực thi. Các Network ACL duy trì tính đơn giản và không trạng thái (stateless), với lượt truy cập công cộng bị từ chối và lưu lượng phản hồi tạm thời chỉ được phép trong phạm vi private subnet.

## 2. IAM & Access Control

### 2.1 Service Roles

Các IAM service roles trong AWS thực thi sự phân tách trách nhiệm nghiêm ngặt. Đặc biệt, không có service role nào có quyền admin hoặc quyền thực hiện các tác vụ phá hủy trên môi trường production:

| Role | Used by | Permissions |
|---|---|---|
| `FinOpsStepFunctionsRole` | Step Functions | `states:StartExecution`, `states:DescribeExecution` |
| `FinOpsCURPullerRole` | `LambdaCURPuller` | `s3:GetObject` (trên CUR S3 bucket của tài khoản đích), `s3:PutObject` (trên raw S3 bucket), `ce:GetCostAndUsage` |
| `FinOpsAiExecutionRole` | AI Engine Lambda | `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`, `secretsmanager:GetSecretValue` (qua SDK), `s3:GetObject` (đọc dữ liệu chi phí từ curated S3 bucket), `s3:PutObject` / `s3:GetObject` (đọc/ghi telemetry & kiểm toán tới S3 Authoritative store), `dynamodb:PutItem` / `dynamodb:UpdateItem` / `dynamodb:GetItem` (Ghi điều kiện DynamoDB trên `finops-idempotency-{env}` và đọc/ghi tới `finops-rollback-cache` và DynamoDB Dashboard Cache) |
| `FinOpsContainmentRole` | `LambdaContainment` | `ec2:CreateTags` (non-prod), `asg:UpdateAutoScalingGroup` (non-prod). Cấu hình explicit deny cho các quyền `iam:*`, `s3:Delete*`, và xóa tài nguyên prod. |

> [!IMPORTANT]
> **Ranh giới Bảo mật Cứng**: Mọi role thực thi của CDO đều đi kèm một Service Control Policy (SCP) để đảm bảo hệ thống **NEVER terminate prod, delete data, hoặc modify IAM**. Các tác vụ containment trên production chỉ giới hạn ở mức tag, suggest, hoặc dry-run kiểm toán.

### 2.2 Lambda Execution Roles

Các hàm AWS Lambda sử dụng các Role thực thi (Execution Roles) để áp dụng nguyên tắc đặc quyền tối thiểu:
1. **Lambda Execution Role** (`FinOpsAiExecutionRole`): Được dịch vụ Lambda sử dụng để chạy mã hàm, kéo hình ảnh container từ ECR và ghi log thực thi vào CloudWatch.
2. **Cô lập quyền truy cập**: Mã ứng dụng chạy bên trong hàm Lambda sử dụng role này để truy vấn Secrets Manager (qua SDK), đọc/ghi vào dữ liệu chi phí curated trong S3, và đọc/ghi tới S3 Authoritative store. Đội ngũ CDO sở hữu role thực thi này như một phần của nền tảng host, trong khi đội AIOps cung cấp các container image được gắn phiên bản.

Workloads không kế thừa quyền từ host. Mỗi hàm Lambda được liên kết rõ ràng với role thực thi tương ứng trong cấu hình hàm.

- **Lambda Function Role Mappings**:

| Tên Hàm | IAM Execution Role | Managed Policies / Custom Scoped Policies |
|---|---|---|
| AI Engine Lambda | `FinOpsAiExecutionRole` | Quyền đọc Secrets Manager (contract keys), S3 đọc/ghi (cost files, audit, và idempotency), CloudWatch Logs ghi log, và quyền ghi DynamoDB (read cache, nếu áp dụng). |

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
  - `finops-engineering-operator`: Thành viên được ủy quyền truy cập chi tiết kỹ thuật, xem kế hoạch thực thi thô và kích hoạt các hành động xác thực khắc phục lập trình (đại diện cho ngữ nghĩa `/v1/verify`) và rollback thủ công (đại diện cho ngữ nghĩa `/v1/audit/{audit_id}/rollback`).
  - `finops-cdo-admin`: Thành viên được cấp quyền quản lý chính sách truy cập, điều chỉnh phân bổ người dùng vào nhóm và cấu hình các cờ kiểm soát nền tảng toàn cục.

### 2.5 Khóa bảo mật ngân sách lỗi (Error Budget Security Lock - LOCKED_MODE)

Để ngăn chặn các hành động tự động containment bị lỗi dây chuyền và bảo vệ tính sẵn sàng của tài nguyên, hệ thống áp dụng cơ chế Khóa bảo mật ngân sách lỗi tự động với các ngưỡng phân tầng:
1. **Điều kiện kích hoạt**: Chuyển Tenant sang trạng thái `LOCKED_MODE` dựa trên phân tầng môi trường:
   - Môi trường `prod`, `prod-core`, và `prod-payments` sẽ khóa nếu tỷ lệ rollback (hoàn tác thủ công do phát hiện False Positive) vượt quá **1% trong cửa sổ 30 ngày liên tục**.
   - Môi trường `staging` sẽ khóa nếu tỷ lệ rollback vượt quá **10% trong cửa sổ 30 ngày liên tục**.
   - Môi trường `dev`, `sandbox`, `ml-research`, và `data-analytics` không kích hoạt khóa (tính năng kiểm tra ngân sách lỗi bị vô hiệu hóa).
2. **Hành vi**:
   - Mọi yêu cầu gửi tới `/v1/decide` sẽ tự động trả về `dry_run_mode: true` và AI Engine từ chối cung cấp payload can thiệp thật.
   - Tất cả các tiêu đề phản hồi (response headers) sẽ bao gồm các trường `X-Containment-Status: LOCKED` và `X-Lock-Reason: error_budget_exceeded_threshold`.
   - Nền tảng CDO bắt buộc chuyển mọi hoạt động containment downstream sang chế độ dry-run (chỉ cảnh báo), bỏ qua mọi nỗ lực ghi đè thủ công.
3. **Khôi phục**: Việc mở khóa trạng thái `LOCKED_MODE` yêu cầu xem xét và phê duyệt thủ công từ Trưởng nhóm AI (AI Team Lead), người phải đặt lại các tham số ngân sách lỗi một cách rõ ràng.

### 2.6 Tiêu chuẩn đặt tên Bucket S3 & Các chế độ truy cập IAM (S3 Telemetry Bucket Naming & IAM Access Modes)

Để lưu trữ dữ liệu đo lường vận hành (telemetry), bằng chứng bất thường trung gian, và nhật ký kiểm toán, các S3 bucket tuân theo quy tắc đặt tên chuẩn hóa sau:
- `company-cdo-{account_id}-telemetry` (trong đó `{account_id}` đại diện cho ID tài khoản AWS của thành viên).

Việc truy cập các telemetry bucket này giữa các tài khoản hỗ trợ hai chế độ cấu hình IAM riêng biệt:
1. **Chế độ per-CDO (Mặc định - per-CDO Mode)**: Mô hình cách ly nghiêm ngặt, đơn bên (single-tenant), trong đó mỗi thực thể CDO platform có quyền đọc/ghi chuyên dụng được giới hạn riêng cho bucket thuộc tài khoản của mình (`company-cdo-{account_id}-telemetry`).
2. **Chế độ khung chia sẻ (Shared Skeleton Mode)**: Mô hình điều phối đa bên (multi-tenant) cho phép chia sẻ dữ liệu telemetry chéo tài khoản. Quyền truy cập được quản lý thông qua:
   - Một chính sách tài nguyên S3 chứa ký tự đại diện (wildcard) được giới hạn bởi các điều kiện AWS (AWS conditions) cho các OU cụ thể của tổ chức.
   - Hoặc gọi chéo tài khoản `STS AssumeRole` đi kèm với một mã định danh ngoại (ExternalId) được tạo động dựa trên tiêu đề `X-Tenant-Id` của tenant, đảm bảo ranh giới thuê bao nghiêm ngặt trong quá trình thu thập dữ liệu đa tài khoản.

## 3. Secrets Management

### 3.1 Secrets Inventory

Các secret sau đây được lưu trữ trong AWS Secrets Manager:

| Secret | Nơi lưu trữ | Chu kỳ xoay vòng | Được truy cập bởi |
|---|---|---|---|
| `finops/ai-engine/api-key` (Hết hiệu lực) | Hết hiệu lực | N/A | Được thay thế bởi thông tin xác thực AWS IAM SigV4 |
| `finops/dashboard/db-creds` | AWS Secrets Manager | Tự động mỗi 60 ngày | Athena Query Engine / QuickSight dataset engine trong tương lai |
| `finops/alerting/slack-webhook` | AWS Secrets Manager | Thủ công mỗi 90 ngày | `LambdaAlertRouting` |
| `finops/ai-engine/contract-signing-key` (Hết hiệu lực) | Hết hiệu lực | N/A | Được thay thế bởi cơ chế kiểm tra toàn vẹn yêu cầu (`X-Payload-SHA256`) |
| `finops/containment/external-id-seed` | AWS Secrets Manager | Xoay vòng thủ công khi xảy ra sự cố | Quy trình cung cấp vai trò containment |

### 3.2 Inject Pattern & Integrity Verification

Vì hệ thống sử dụng AWS IAM SigV4 để xác thực giữa các dịch vụ thay vì static API keys, private ALB/HTTPS adapter sẽ xác thực thông tin đăng nhập của yêu cầu. Hàm AI Engine container xác thực tính toàn vẹn của yêu cầu, độ lệch thời gian và ranh giới thuê bao trực tiếp từ các tiêu đề chéo: `X-Tenant-Id`, `X-Idempotency-Key`, `X-Payload-SHA256`, `X-Request-Timestamp`, và `X-Dry-Run-Mode`.

Hệ thống áp dụng chính sách tách biệt về độ lệch thời gian (clock-skew split policy):
1. **Độ lệch thời gian của yêu cầu API**: Độ lệch của tiêu đề `X-Request-Timestamp` được giới hạn nghiêm ngặt ở mức **300 giây** để chống lại các cuộc tấn công phát lại (replay attacks). Các yêu cầu nằm ngoài cửa sổ này sẽ tự động bị từ chối.
2. **Độ trễ truyền dữ liệu CUR đầu vào**: Độ trễ thời gian lên tới **36 giờ** đối với dữ liệu chi phí (tệp xuất CUR trong S3) là bình thường và được chấp nhận do độ trễ cập nhật hóa đơn tiêu chuẩn của đám mây, và không kích hoạt lỗi xác thực độ lệch thời gian hay phát lại.

Các kiểm tra idempotency hot-path được thực hiện đối với bảng DynamoDB `finops-idempotency-{env}` sử dụng ghi điều kiện (conditional writes) và TTL 24 giờ (`ttl_expiry`), thay vì lưu trữ các khóa idempotency trong S3. S3/Object Lock được dành riêng cho các log kiểm toán dài hạn, telemetry sao lưu, và bằng chứng rollback.

Ví dụ, hàm container Lambda xác thực yêu cầu đi vào và thực hiện DynamoDB conditional write bằng đoạn mã logic Python sau:

```python
import time
import hashlib
import boto3
from datetime import datetime
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')

def validate_request_integrity(event):
    headers = event.get("headers", {})
    body = event.get("body", "")
    
    # 1. Verify Contract Headers
    req_timestamp_str = headers.get("X-Request-Timestamp")
    idempotency_key = headers.get("X-Idempotency-Key")
    payload_hash = headers.get("X-Payload-SHA256")
    tenant_id = headers.get("X-Tenant-Id")
    dry_run_mode = headers.get("X-Dry-Run-Mode", "true")
    
    if not all([req_timestamp_str, idempotency_key, payload_hash, tenant_id]):
        return {"statusCode": 400, "body": "Missing required contract headers"}
        
    # 2. Verify Clock Skew (max 300s)
    req_time = datetime.fromisoformat(req_timestamp_str.replace("Z", "+00:00"))
    now = datetime.now(req_time.tzinfo)
    drift = abs((now - req_time).total_seconds())
    if drift > 300:
        return {"statusCode": 400, "body": "ERR_REPLAY_DETECTED: Clock skew > 300 seconds"}
        
    # 3. Verify Payload Hash
    calculated_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if payload_hash != calculated_hash:
        return {"statusCode": 400, "body": "ERR_PAYLOAD_MISMATCH: Hash mismatch"}
        
    # 4. DynamoDB Conditional Write (Idempotency Hot Path)
    table = dynamodb.Table('finops-idempotency-prod')
    ttl_expiry = int(time.time()) + 86400  # 24h TTL
    
    try:
        table.put_item(
            Item={
                'idempotency_key': idempotency_key,
                'payload_sha256': payload_hash,
                'status': 'IN_PROGRESS',
                'tenant_id': tenant_id,
                'ttl_expiry': ttl_expiry
            },
            ConditionExpression='attribute_not_exists(idempotency_key)'
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return {"statusCode": 409, "body": "ERR_IDEMPOTENCY_CONFLICT: Key already exists"}
        raise e
        
    return {"statusCode": 200}
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
| Dữ liệu chi phí Raw/Curated | S3 | `aws/s3` hoặc CMK tùy chỉnh | Bật tính năng S3 Bucket Key để giảm thiểu chi phí gọi KMS API. Giới hạn trong `company-cdo-{account_id}-telemetry`. |
| Run State Cache & Dashboard Cache | DynamoDB | `aws/dynamodb` hoặc CMK tùy chỉnh | Mã hóa sử dụng KMS. Bao gồm `finops-idempotency-{env}` và `finops-rollback-cache`. |
| Secrets Store | Secrets Manager | `finops-secrets-key` | Việc giải mã yêu cầu chính sách role trust rõ ràng. |
| Lưu trữ tạm thời / Container Lambda | Bộ lưu trữ Lambda | `aws/lambda` hoặc CMK tùy chỉnh | Toàn bộ dung lượng lưu trữ tạm thời của hàm (bao gồm /tmp lên đến 10 GB) được mã hóa mặc định. |
| Nhật ký kiểm toán & Idempotency Store | S3 Object Lock / S3 | `finops-audit-key` | Lưu trữ audit trên S3/Object Lock là đáng tin cậy nhất; lưu giữ tối thiểu 90 ngày. |

### 4.2 In Transit

- **Yêu cầu TLS**: Tất cả traffic đi vào và đi ra đều yêu cầu mã hóa TLS 1.3 (với TLS 1.2 là phiên bản tối thiểu được chấp nhận).
- **Traffic nội bộ**: Giao tiếp function-to-function và tin nhắn SQS được mã hóa hoàn toàn khi truyền tải natively bởi các dịch vụ AWS sử dụng TLS.
- **Các cuộc gọi AI Engine**: Step Functions và compute nền tảng gọi endpoint ALB nội bộ riêng tư bằng HTTPS và xác thực AWS SigV4, định tuyến các yêu cầu tới hàm AI Engine Lambda trong private subnets. Payload yêu cầu bao gồm một phiên bản hợp đồng và ID tương quan, và payload sẽ được xác thực bên trong môi trường thực thi của hàm.
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
  "rollback_status": "success",
  "rollback_executed_at": "2026-06-23T07:25:00Z",
  "boto3_result": {
    "HTTPStatusCode": 200,
    "ResponseMetadata": {
      "RequestId": "7f89b910-c123..."
    }
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

Bản ghi kiểm toán được ghi lại trước khi thực hiện bất kỳ hoạt động apply nào và được cập nhật sau hoạt động đó với trạng thái cuối cùng. Khi hoạt động rollback được thực thi, nhật ký kiểm toán sẽ được cập nhật thêm các trường dành riêng cho rollback bao gồm `rollback_status`, `rollback_executed_at` và trường tùy chọn `boto3_result` chứa phản hồi API thô từ AWS. Mọi bản ghi hành động containment đều được liên kết mã hóa với bản ghi trước đó trong một chuỗi append-only lưu trữ tại kho lưu trữ S3 đáng tin cậy (với tùy chọn đồng bộ cache lên DynamoDB), với mã băm kiểm tra toàn vẹn được tính toán là `sha256(current_payload + previous_hash)` nhằm đảm bảo khả năng chống giả mạo (tamper-evident). Hoạt động dry-run vẫn tạo ra các bản ghi kiểm toán vì Finance cần xem nền tảng sẽ làm gì và tại sao hành động đó vẫn an toàn. Bộ dữ liệu huấn luyện mô hình AI không được CDO ghi nhật ký; CDO chỉ ghi nhật ký metadata cuộc gọi, các trường quyết định được trả về và các tham chiếu bằng chứng vận hành cần thiết cho việc cảnh báo và containment. Dữ liệu đo lường hiệu năng gửi tới AI Engine để phát hiện bất thường là dạng lai (hybrid), bao gồm các tệp xuất S3 CUR, dữ liệu API Cost Explorer và các chỉ số hiệu năng từ CloudWatch (`resource_utilization_metrics` như CPU, memory, network, disk, database connections, và GPU metrics). Nếu các chỉ số CloudWatch không khả dụng, hệ thống tự động chuyển sang chế độ CUR-only, thiết lập `data_confidence = LOW` và bắt buộc thực hiện các hành động containment ở chế độ dry-run/alert-only. Các tệp log và metrics của CloudWatch cũng được sử dụng cho việc giám sát sức khỏe vận hành của CDO platform và cảnh báo SRE. Mọi hoạt động xác thực bảng điều khiển (đăng nhập thành công, đăng xuất, làm mới phiên hết hạn), lỗi xác thực (đăng nhập thất bại, chữ ký token không hợp lệ, vi phạm cửa sổ replay) và các nỗ lực truy cập nhóm không được ủy quyền (như người dùng Finance readonly cố gắng gọi một hành động của operator) đều được ghi nhật ký ngay lập tức vào CloudWatch Logs và truyền về S3 để lưu giữ lịch sử kiểm toán.

### 5.2 Storage + Retention

Nhật ký kiểm toán được lưu trữ bảo mật với các cấu hình chống ghi đè:

| Loại Log (Log type) | Nơi lưu trữ | Retention | Giao diện truy vấn |
|---|---|---|---|
| Containment Audits | S3 + Object Lock | Tối thiểu 90 ngày | Athena / DynamoDB (read cache) |
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
