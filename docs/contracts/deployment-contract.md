# Deployment Contract — Task Force 2 (FinOps Watch)

<!-- Owner: Nhóm AI — TF2 FinOps Watch
     Signed by: AI Lead + CDO Lead (CDO-01) + CDO Lead (CDO-02) + Reviewer Panel
     Date signed: 2026-06-25 (W11 T5)
     🔒 FREEZE — Không thay đổi nếu không có Formal Change Request được cả hai bên ký -->

---

## Mục lục

1. [Mục đích & Phạm vi](#mục-đích)
2. [Nguyên tắc cốt lõi](#key-principle)
3. [Đặc tả Compute](#compute)
4. [Đặc tả Scaling](#scaling)
5. [Quản lý Secrets & Credentials](#secrets)
6. [Cấu hình Networking & An ninh mạng](#networking)
7. [Deployment Topology Diagram](#deployment-topology-diagram)
8. [Phân định Môi trường triển khai per-CDO](#per-cdo-deployment)
9. [Chiến lược Rollout: Canary](#rollout-strategy-canary)
10. [Cơ chế Rollback (Hoàn tác)](#rollback)
11. [Health Check Specification](#health-check)
12. [Observability & Tracing](#observability)
13. [Failure Modes & Phản ứng Sự cố](#failure-modes--response)
14. [Giải đáp các câu hỏi mở (Resolved Questions)](#resolved-questions)

---

## Mục đích

Định nghĩa **AI Engine cần được deploy như thế nào** - bao gồm compute target, scale, secrets, network, và chiến lược rollback. Đây là tài liệu đặc tả kỹ thuật chuẩn hóa để **mỗi nhóm CDO tự động hóa quy trình triển khai AI Engine lên nền tảng của mình** và cấu hình tài nguyên (sizing capacity) chính xác.

---

## Key principle

**Nhóm AI bàn giao engine dưới dạng artifact (Container Image đăng ký trên ECR) kèm bản spec triển khai này. MỖI CDO trong Task Force tự deploy engine lên platform riêng của mình** (ví dụ: CDO-01 dùng Serverless/ECS Fargate, CDO-02 dùng AWS App Runner / ECS Fargate... - mỗi CDO một góc tiếp cận kỹ thuật khác nhau và compete ở cách host, giám sát và tối ưu vận hành). 

Các thông số kỹ thuật bên dưới là **spec tham chiếu tối thiểu CDO phải đáp ứng** (CDO Fargate/App Runner map sang ECS Task / App Runner instance / Lambda - miễn là năng lực xử lý tương đương). Mỗi CDO sở hữu **endpoint riêng**, mỗi instance được cách ly dữ liệu multi-tenant hoàn toàn dựa trên `tenant_id`.

> 💡 **Cơ chế Bootstrap Tạm thời:** Trong ngày T5 W11 đến đầu W12, nhóm AI cung cấp **1 skeleton endpoint dùng chung** để CDO tích hợp trước code path (giao diện mock). W12 mỗi CDO bắt buộc phải deploy instance thật từ artifact của nhóm AI lên platform riêng của mình để đánh giá E2E.

---

## Compute

Triển khai container hóa hoàn toàn dựa trên đặc tả cấu hình tài nguyên:

| Thuộc tính (Aspect) | Cấu hình tham chiếu (Configuration) | Mô tả (Description) |
|---|---|---|
| **Target Compute** | ECS Fargate Task / App Runner Instance / Lambda | Đảm bảo tính cô lập, không dùng shared VM |
| **Cluster Name** | `tf-2-aiops-cluster` | Tên cluster định danh theo Task Force (nếu dùng ECS) |
| **Service Name** | `ai-engine` | Tên dịch vụ đăng ký DNS nội bộ |
| **Image Source** | `200000000012.dkr.ecr.ap-southeast-1.amazonaws.com/tf2/finops-ai-engine` | URI ECR của container image |
| **CPU per task** | 1024 (1 vCPU) | Đảm bảo đủ hiệu năng xử lý DataframeCUR thô |
| **Memory per task** | 2048 MB (2 GB) | Giới hạn bộ nhớ đệm tránh rò rỉ (OOM protection) |

---

## Scaling

Cấu hình tự động co giãn tải (Auto-scaling) đảm bảo tính sẵn sàng và tối ưu hóa chi phí vận hành:

| Thuộc tính (Aspect) | Giá trị đặc tả (Value) | Ghi chú (Notes) |
|---|---|---|
| **Min Replicas** | 2 | Luôn duy trì tối thiểu 2 task trên 2 AZs để đảm bảo High Availability |
| **Max Replicas** | 10 | Giới hạn trên để tránh cháy ngân sách hạ tầng (Budget Guard) |
| **Scale-up Trigger 1** | Target CPU Utilization $\ge 70\%$ | Dựa trên chỉ số CPU sử dụng trung bình |
| **Scale-up Trigger 2** | Target Request Count $\ge 100$ per task | Tránh nghẽn hàng đợi xử lý khi CDO gọi batch |
| **Scale-up Cooldown** | 60 giây | Thời gian chờ giữa các lần tăng số lượng task |
| **Scale-down Cooldown** | 300 giây | Tránh hiện tượng co giãn liên tục gây bất ổn (Thrashing) |
| **Cold Start Mitigation** | Provisioned Concurrency = 2 | Chỉ áp dụng nếu CDO chọn deployment target là AWS Lambda |

---

## Secrets

Quản lý thông tin nhạy cảm tập trung, cấm hardcode credentials trong container:

| Tên biến (Secret Name) | Nguồn cung cấp (Source) | Mô tả (Description) |
|---|---|---|
| `BEDROCK_API_KEY` | AWS Secrets Manager: `tf-2/ai-engine/bedrock` | API Key sơ cua (hoặc Token) nếu gọi qua API Gateway ngoài. Mặc định ưu tiên IAM Role. |
| `AWS_REGION` | Environment Variable | Thiết lập mặc định: `ap-southeast-1` (Singapore) |
| `DYNAMODB_TABLE_NAME` | Environment Variable | Tên bảng DynamoDB lưu audit trail cache |

> 🔒 **Quy tắc an toàn mạng:** Tuyệt đối không sử dụng IAM User static access key. Toàn bộ hạ tầng của CDO phải gán IAM Task Execution Role có gắn Policy cho phép truy cập Bedrock và Secrets Manager. Secrets Manager rotation policy được thiết lập tự động xoay vòng mỗi 30 ngày.

---

## Networking

AI Engine chạy trong Private Subnet, ngăn chặn tấn công từ internet public:

| Thuộc tính (Aspect) | Cấu hình mạng (Configuration) |
|---|---|
| **Subnet Type** | Private Subnets (Isolated/Non-routable to internet) |
| **Load Balancer** | Internal Application Load Balancer (ALB) only. Cấm Internet-facing ALB. |
| **Security Group** | `tf-2-ai-engine-sg` |
| **Ingress Rules** | Chỉ cho phép giao thức HTTPS (port 8080/443) đi từ Security Group của CDO Worker/Platform gọi đến AI Engine |
| **Egress Rules** | Chỉ cho phép đi ra Internet qua NAT Gateway tới Bedrock Endpoint (`bedrock.ap-southeast-1.amazonaws.com`) và các VPC Gateway Endpoints cho Secrets Manager + DynamoDB |
| **DNS Resolution** | Sử dụng Route 53 Private Hosted Zone để phân giải tên miền nội bộ |

---

## Deployment topology diagram

Kiến trúc triển khai song song hai platform độc lập của CDO-01 và CDO-02 cùng chia sẻ một Artifact từ nhóm AI:

```mermaid
graph TB
    AIO["Nhóm AI: engine artifact (image) + Deployment Contract"]
    
    subgraph CDO_1["CDO-01 Platform (vd Serverless/ECS Fargate)"]
        E1["AI engine Task Instance (Fargate)"]
        I1["CDO-1 Infra: Alert pipeline, Dashboard, Observability"]
        I1 -->|Call Local IP| E1
        E1 --> SM1["Secrets Manager VPC Endpoint"]
    end
    
    subgraph CDO_2["CDO-02 Platform (vd AWS App Runner / ECS Fargate)"]
        E2["AI engine Task Instance (Fargate / App Runner)"]
        I2["CDO-2 Infra: Prometheus, Grafana, EventBridge"]
        I2 -->|Call Service Endpoint| E2
        E2 --> SM2["Secrets Manager VPC Endpoint"]
    end
    
    AIO -. Cung cấp Container Image .-> E1
    AIO -. Cung cấp Container Image .-> E2
    E1 --> Bedrock["AWS Bedrock (Nova Pro)"]
    E2 --> Bedrock["AWS Bedrock (Nova Pro)"]
    
    classDef platform fill:#f5f5f7,stroke:#c8c8cc,stroke-width:1px;
    class CDO_1,CDO_2 platform;
```

---

## Per-CDO deployment

Mỗi CDO thiết lập DNS nội bộ riêng để phân phối request tới instance của mình:

| CDO Platform | Tên miền Endpoint nội bộ (VPC) | Phương thức xác thực |
|---|---|---|
| **CDO-01** (Fargate) | `https://ai-engine.cdo-01.tf-2.internal/` | AWS IAM SigV4 |
| **CDO-02** (App Runner / ECS Fargate) | `https://ai-engine.cdo-02.tf-2.internal/` | AWS IAM SigV4 |
| *(Bootstrap)* Skeleton chung | `https://ai-engine-skeleton.tf-2.internal/` (Chỉ dùng từ T5 đến đầu W12) | AWS IAM SigV4 |

---

## Chiến lược Rollout: Canary

Áp dụng khi triển khai phiên bản mới của AI Engine nhằm kiểm soát rủi ro phát sinh lỗi:

| Bước (Step) | Tỷ lệ Traffic chuyển tiếp | Thời gian theo dõi (Interval) |
|---|---|---|
| 1 | 10% | 5 phút |
| 2 | 50% | 5 phút |
| 3 | 100% (Hoàn tất chuyển đổi) | - |

⛔ **Chỉ số kích hoạt Hủy bỏ (Abort Criteria)** (bất kỳ điều kiện trigger → auto rollback ngay):
- Tỷ lệ lỗi hệ thống (Error rate / 5xx) > 1% trong cửa sổ 5 phút.
- Độ trễ phản hồi P99 (P99 latency) > 800 ms cho các API chính.
- Cảnh báo tốc độ cháy ngân sách nhanh bị kích hoạt (Burn-rate fast alert triggered).
- Phát hiện lỗi liên quan đến mô hình hoặc Bedrock Throttling Rate >= 20%.

---

## Cơ chế Rollback (Hoàn tác)

Quy định phương thức khôi phục trạng thái cũ nhanh nhất khi xảy ra lỗi nghiêm trọng:
 
| Thuộc tính (Aspect) | Giá trị đặc tả (Value) |
|---|---|
| **Primary method** | AWS CodeDeploy / ECS Service Update automatic rollback (CDO-01 Fargate & CDO-02 App Runner / Fargate) |
| **Secondary method** | ECS service revert / App Runner previous version redeploy (manual) |
| **Target RTO** | < 60 giây |
| **Auto-trigger** | Yes (khi abort criteria met trong canary rollout) |
 
 ---
 
 ## Health check
 
 ALB/App Runner Health Checking Agent gọi định kỳ để xác định trạng thái sống/chết của container:
 
 | Thuộc tính (Field) | Giá trị đặc tả (Value) |
 |---|---|
 | **Path** | `/health` (Theo đặc tả tại `ai-api-contract.md` §5.4) |
 | **Port** | 8080 |
 | **Interval** | 30 giây |
 | **Healthy threshold** | 2 consecutive 200 (2 lần liên tiếp trả về HTTP code 200) |
 | **Unhealthy threshold** | 3 consecutive non-200 (3 lần liên tiếp trả về HTTP code non-200) |
 
 ---
 
 ## Observability
 
 Đảm bảo giám sát tập trung phục vụ vận hành và xử lý sự cố nhanh:
 
 | Thuộc tính (Aspect) | Cấu hình (Configuration) |
 |---|---|
 | **OTel endpoint** | Collector URL per CDO platform (cấu hình qua biến môi trường `OTEL_EXPORTER_OTLP_ENDPOINT`) |
 | **Log destination** | CloudWatch Logs (retention 14 ngày) |
 | **Metrics** | Prometheus format `/metrics` / CloudWatch (CDO tự chọn phù hợp hạ tầng) |
 | **Traces** | OpenTelemetry → AWS X-Ray (cho cả CDO-01 và CDO-02) |
 
 ---
 
 ## Failure modes & phản ứng sự cố
 
 | Lỗi phát sinh (Failure) | Cơ chế phát hiện (Detection) | Hành động ứng phó (Response) |
 |---|---|---|
 | **Task / Container crash** | ECS Health check / App Runner Health probe | Tự động khởi động lại (Auto-restart task/instance). |
 | **Lỗi mạng diện rộng (Region outage)** | CloudWatch Route53 Health check / DNS Failover alarm | Định tuyến failover sang Secondary Region (Active-Passive). |
 | **Bedrock throttling** | HTTP Code 429 (App-level metric) | Tự động kích hoạt **Exponential Backoff với Jitter**, nếu kéo dài >15s → Rule-based Fallback. |
 | **Rò rỉ bộ nhớ (Memory leak)** | Bộ nhớ container đạt ngưỡng $\ge 90\%$ | Thực hiện khởi động lại luân phiên (Rolling restart). |

## Open questions (Đã làm rõ / Clarified)

- [x] **Q1: Multi-region cho disaster recovery - có trong scope capstone không?**
  - *Giải đáp*: **Không thuộc scope bắt buộc của Capstone**. Tuy nhiên, kiến trúc đa vùng (Multi-region Active-Passive) có thể được CDO triển khai tự do làm điểm nhấn kỹ thuật (Differentiation Angle) để ghi điểm cộng với Panel đánh giá.
- [x] **Q2: Cost cap per task force per ngày - đặt mức nào?**
  - *Giải đáp*: Ngân sách hoạt động cho Bedrock API của toàn bộ Task Force được khống chế ở mức **$50 USD / tháng** (tương đương ~$1.67 USD / ngày). CDO Platform cần cấu hình alarm cảnh báo chi phí ở mức 80% ($1.33 USD / ngày) và ngắt mạch (Circuit Breaker) dừng gọi Bedrock ở mức 100% ($1.67 USD / ngày).