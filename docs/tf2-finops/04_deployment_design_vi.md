# Thiết kế Triển khai và CI/CD (Deployment & CI/CD Design) - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Final (W11 T6 Pack #1) → Updated (W12 T4 Pack #2)
-->

## 1. IaC strategy

### 1.1 Tool choice

CDO platform sử dụng chiến lược triển khai hai lớp để phân tách rõ ràng giữa việc thiết lập hạ tầng và việc triển khai các ứng dụng chạy trên đó.
1. **Lớp hạ tầng (AWS Resources)**: Sử dụng **Terraform (v1.5+)** để khởi tạo các tài nguyên bất biến (VPC, EKS cluster, node groups, DynamoDB, S3, IAM roles).
2. **Lớp ứng dụng (Kubernetes & Applications)**: Sử dụng **Helm (v3)** và **GitOps (ArgoCD)** đối với các trạng thái ứng dụng trong cụm EKS, và cơ chế đóng gói tệp zip tiêu chuẩn để triển khai cho các hàm Lambda.

Terraform sở hữu nền tảng AWS: mạng, các bucket lakehouse, siêu dữ liệu Glue/Athena, Step Functions, Lambda wrapper, các bảng DynamoDB, role IAM, EKS control plane, các managed node groups, ECR repository, nền tảng IRSA/OIDC, các điều kiện cần thiết cho load-balancer nội bộ và phân phối secrets. Trạng thái mong muốn của Kubernetes trong thời gian chạy được quản lý thông qua lớp GitOps, do đó các manifest ứng dụng và Helm value có thể di chuyển độc lập với các module hạ tầng trong khi vẫn phụ thuộc vào đầu ra của Terraform.

### 1.2 Module structure

Cấu trúc thư mục mã nguồn được phân chia rõ ràng giữa các modules định nghĩa tài nguyên và cấu hình môi trường cụ thể:

Ranh giới module được cố ý định hướng theo dịch vụ thay vì định hướng theo nhóm. Các mối quan tâm chung của nền tảng như KMS key, VPC endpoint, chính sách IAM và khả năng quan sát (observability) là các module có thể tái sử dụng, trong khi các thư mục môi trường gốc chỉ cung cấp định cỡ (sizing), account ID, feature flag và các biến nhạy cảm cần phê duyệt. Điều này ngăn các phím tắt sandbox rò rỉ vào staging hoặc prod.

```
├── iac/
│   ├── modules/
│   │   ├── vpc/                  # Thiết lập VPC riêng tư, subnets, NAT gateways, VPC endpoints
│   │   ├── eks/                  # Cụm EKS control plane, on-demand/spot node groups
│   │   ├── s3-lakehouse/         # S3 raw và curated buckets, lifecycle policies
│   │   ├── glue-catalog/         # Khởi tạo Glue databases và tables
│   │   ├── step-functions/       # Định nghĩa các trạng thái workflow của Step Functions
│   │   ├── lambdas/              # Các mã nguồn Lambda (CUR puller, routing, containment)
│   │   └── dynamodb/             # Bảng DynamoDB lưu run state, idempotency, và audit logs
│   └── environments/
│       ├── sandbox/              # File biến cấu hình sandbox (.tfvars)
│       ├── staging/              # File biến cấu hình staging
│       └── prod/                 # File biến cấu hình production
```

### 1.3 State management

- **Lưu trữ State từ xa (Remote State)**: State của Terraform được lưu trữ trong một bucket S3 an toàn, tập trung với mã hóa phía máy chủ, bật phiên bản (versioning) và các khóa state cụ thể cho từng môi trường.
- **Khóa State (State Locking)**: Các thư mục môi trường gốc chạy lâu dài sử dụng tính năng khóa file của S3 backend (`use_lockfile = true`) để tránh việc dùng một bảng khóa DynamoDB riêng biệt.
- **Tiếp nhận GitOps (GitOps Ingestion)**: Đầu ra plan được tạo trên PR (`plan-on-PR`) và các job apply tiêu thụ các plan artifact đã được xem xét thay vì tính toán lại các thay đổi chưa được xem xét.
- **Truy cập State**: Các role CI chỉ có thể đọc/ghi khóa state cho môi trường đích. Các nhà phát triển có thể chạy xác thực cục bộ, nhưng các lệnh apply trên staging và prod phải được thực thi bởi CI với OIDC và kiểm soát môi trường.

## 2. CI/CD pipeline

### 2.1 Pipeline stages

Các pipeline triển khai được thúc đẩy bởi GitHub Actions. Luồng công việc bao gồm biên dịch, xác thực, kiểm tra bảo mật, triển khai sandbox từ `develop`, triển khai staging từ `main` và triển khai production chỉ thông qua cổng phê duyệt thủ công:

```
[PR Trigger] ──> Lint & Verify ──> Security Scan (Trivy/Gitleaks) ──> TF Plan ──> [Merge Approval]
                                                                                      │
[Smoke Test Prod] <── TF Apply Prod <── [Manual Approval Gate] <── Deploy Staging <───┘
```

Các bước chi tiết trong pipeline được mô tả dưới đây:

| Giai đoạn (Stage) | Công cụ (Tool) | Nhiệm vụ | Chỉ tiêu chất lượng (Quality gate) |
|---|---|---|---|
| Lint & Verify | `tflint`, `helm lint` | Kiểm tra cú pháp Terraform và các Helm charts. | Không có lỗi cú pháp nào. |
| Quét bảo mật | Trivy / Gitleaks | Quét các lỗ hổng CVE trong Docker images và Helm charts; phát hiện secret bị lộ. | Dừng build nếu phát hiện lỗi CVE mức `CRITICAL` hoặc `HIGH`; 0 secret bị lộ. |
| TF Plan | Terraform | Khởi chạy plan thử nghiệm để so sánh thay đổi hạ tầng trên AWS. | Thực thi plan thành công và xuất báo cáo. |
| Triển khai Sandbox | Terraform / ArgoCD | Áp dụng các thay đổi đã được phê duyệt từ `develop` vào sandbox để tích hợp nhanh. | Triển khai Terraform thành công; smoke test cốt lõi vượt qua. |
| Smoke Test Sandbox | Kịch bản Python riêng | Chạy một sự kiện tích hợp tổng hợp thông qua thu thập, xác thực hợp đồng AI, định tuyến cảnh báo và ghi sổ kiểm toán. | Bản ghi kiểm toán dry-run và cảnh báo kiểm thử được tạo ra. |
| Triển khai Staging | Terraform / ArgoCD | Áp dụng các thay đổi đã được xem xét từ `main` vào staging và đồng bộ hóa trạng thái mong muốn của EKS workload. | Trạng thái Pod trong EKS đạt `Running`; Step Functions smoke run thành công; không bị drift. |
| Manual Approval Gate | GitHub Environment Gate | Tạm dừng pipeline lên production, chờ phê duyệt thủ công từ CDO Lead hoặc reviewer được ủy quyền. | Chữ ký của người xem xét thủ công và plan artifact đã xem xét. |
| Triển khai Prod | Terraform / ArgoCD | Chỉ áp dụng plan production đã được xem xét. Containment trên prod vẫn chỉ giới hạn ở tag/suggest/dry-run. | 0 lỗi, không có thay đổi dữ liệu/IAM mang tính phá hủy, dry-run kiểm toán thành công. |
| Smoke Test Prod | Kịch bản Python riêng | Thực thi một chuỗi dry-run an toàn trên production. | Không có containment ở chế độ apply; bản ghi kiểm toán được ghi lại thành công. |

### 2.2 Branch strategy

- `feature/*`: Các nhánh chuyên dụng cho tính năng. PR target: `develop`; chỉ xác thực, không apply lên cloud.
- `develop`: Nhánh tích hợp sandbox. Lệnh push vào `develop` có thể tự động áp dụng cho sandbox sau khi vượt qua các bước kiểm tra.
- `main`: Nhánh staging. Lệnh merge từ `develop` vào `main` kích hoạt triển khai staging và xác thực tích hợp đầy đủ.
- `prod`: Đường dẫn release production. Áp dụng lên production không bao giờ tự động; nó sử dụng phê duyệt môi trường của GitHub, plan artifact đã xem xét và cấu hình containment an toàn trên prod.

## 3. Deployment gates

### 3.1 Security scans

Bên cạnh việc quét mã nguồn tĩnh, các kho lưu trữ ECR được bật cấu hình **Scan on Push**. Mọi image do AIOps đẩy lên sẽ được tự động quét lỗi bảo mật. Việc deploy lên EKS sẽ bị chặn lại nếu image chứa các lỗ hổng bảo mật nghiêm trọng. Pipeline CI/CD xác thực với tài khoản AWS thông qua giao thức **OpenID Connect (OIDC)**, loại bỏ việc lưu trữ cố định các AWS Access Keys trên GitHub.

Cổng bảo mật cũng kiểm tra các plan Terraform, Helm chart, manifest Kubernetes, dependency của Lambda và image container. Các bước kiểm tra bắt buộc bao gồm `terraform fmt`, `terraform validate`, TFLint, quét IaC bằng Checkov hoặc tương đương, quét image bằng Trivy, quét secret bằng Gitleaks và kiểm tra chính sách ngăn chặn việc expose AI Engine ra công cộng. Bất kỳ phát hiện CRITICAL nào cũng chặn triển khai trừ khi có ngoại lệ capstone được ghi chép và phê duyệt.

### 3.2 Destructive-change review

Bất kỳ Terraform plan nào hiển thị cảnh báo thay đổi index tài nguyên hoặc có hành động xóa/khởi tạo lại (như tạo lại S3 bucket hoặc thay đổi IAM role) sẽ được gắn nhãn cảnh báo trong PR. Các thay đổi này bắt buộc phải có sự xác nhận thủ công và phê duyệt kép (dual approvals) từ CDO Lead và Security Lead.

Cổng destructive-change nghiêm ngặt hơn đối với các tài nguyên có lưu trạng thái (stateful). Các bucket S3, bảng DynamoDB, KMS key, EKS cluster, node group, IAM role và bộ lưu trữ kiểm toán yêu cầu sự xác nhận của người xem xét khi có sự thế hoặc xóa xuất hiện trong plan. Các plan production phải bị hủy nếu chúng cố gắng terminate tài nguyên prod, xóa dữ liệu hoặc thay đổi IAM bên ngoài tập hợp module đã được phê duyệt.

### 3.3 AI contract compatibility

Trước khi cập nhật container trong EKS, pipeline sẽ khởi chạy một tập lệnh kiểm tra độ tương thích:
1. Đối chiếu model version đăng ký từ AIOps với cấu hình EKS hiện tại.
2. Kiểm tra JSON schema của API contract đầu vào và đầu ra tại endpoint `/detect` của AI Engine.
3. Nếu schema không tương thích, quá trình build sẽ bị dừng ngay lập tức trước khi tác động vào cụm Kubernetes, đảm bảo tính nhất quán của hệ thống.

Việc kiểm tra khả năng tương thích không đánh giá chất lượng mô hình hoặc kiểm tra dữ liệu huấn luyện của AIOps. Nó chỉ xác thực hợp đồng vận hành mà CDO phụ thuộc vào: sức khỏe endpoint, request schema, response schema, các trường bắt buộc, trường phiên bản mô hình, hành vi timeout và các chế độ lỗi. Nếu AI Engine không khả dụng hoặc không tương thích, việc triển khai CDO chỉ có thể tiếp tục đối với các thay đổi hạ tầng mà không kích hoạt các đường dẫn áp dụng containment.

## 4. Deployment strategy

### 4.1 Strategy

- **EKS API Workloads**: Sử dụng chiến lược **Rolling Updates** với cấu hình max surge `25%` và max unavailable `0%`. Điều này đảm bảo các pod chạy ổn định (`ai-engine-api`) luôn có replica mới sẵn sàng trước khi thu hồi các pod cũ.
- **EKS Batch Workers**: Các Kubernetes Jobs thực thi động. Các cập nhật về cấu hình worker sẽ áp dụng cho các lượt gọi job tiếp theo mà không làm ảnh hưởng đến các job đang chạy.
- **Lambda Functions**: Triển khai theo cơ chế **Weighted Aliases**. Traffic được chuyển dịch dần dần: chạy thử nghiệm canary `10%` traffic trong 5 phút, và tự động chuyển sang `100%` nếu không phát sinh lỗi.
- **Spot Node Draining**: Sử dụng Karpenter để xử lý ngắt spot nodes. Khi có tín hiệu ngắt từ EC2, Karpenter sẽ phát tín hiệu trục xuất (evict) pod để drain các pod worker một cách an toàn. Nếu một job batch scoring đang chạy bị dừng giữa chừng, orchestrator sẽ tự động phát hiện và chạy lại ở node healthy khác.

### 4.2 Rollback method

- **Rollback chính**: Thực hiện qua ArgoCD. Việc hoàn tác (revert) một commit Git về SHA ổn định trước đó sẽ tự động kích hoạt ArgoCD đồng bộ lại cấu hình trong cụm EKS trong vòng 60 giây.
- **Rollback phụ**: Đối với các hàm Lambda, workflow Step Functions sẽ bắt các mã lỗi gọi function và ngay lập tức chuyển trọng số (weight) của Lambda alias về phiên bản ổn định trước đó (RTO < 10 giây).
- **Rollback hạ tầng (Infrastructure Rollback)**: Rollback Terraform được xem xét qua plan thay vì chạy tự động. Các tài nguyên lưu trạng thái được bảo toàn, `prevent_destroy` vẫn được bật nếu được hỗ trợ và bất kỳ hoạt động rollback hạ tầng EKS nào cũng phải tính đến các dependency của node group, IRSA và endpoint nội bộ.
- **Kích hoạt Runbook (Runbook Trigger)**: Rollback được kích hoạt bởi smoke test thất bại, xác thực hợp đồng AI thất bại, tỷ lệ lỗi Step Functions tăng cao, các node group EKS không khỏe mạnh hoặc dữ liệu dashboard cũ sau khi triển khai.

## 5. Environment separation

Hạ tầng được cô lập hoàn toàn trên ba tài khoản AWS độc lập:

| Môi trường (Env) | Mục đích sử dụng | Tài khoản AWS | Auto-deploy |
|---|---|---|---|
| **Sandbox** | Vòng lặp nhanh, integration smoke tests và các ví dụ containment trên non-prod. | `1111-2222-3333` | Đúng, từ `develop` sau khi các kiểm tra vượt qua |
| **Staging** | Xác thực các container artifact của AIOps, EKS hosting và chạy E2E pipeline của Step Functions. | `4444-5555-6666` | Đúng, từ `main` sau khi merge đã xem xét |
| **Prod** | Control plane production. Giám sát các tài khoản công ty được phê duyệt. Auto-containment nghiêm ngặt chỉ ở mức tag/suggest/dry-run. | `7777-8888-9999` | Sai, yêu cầu phê duyệt môi trường GitHub |

Các giá trị cụ thể cho từng môi trường chỉ nằm trong `environments/*`. Sandbox có thể kích hoạt các ví dụ chế độ apply hạn chế trên non-prod; staging xác thực hành vi dry-run và tích hợp; prod phải tắt chế độ apply containment theo mặc định.

## 6. Secrets in pipeline

Secrets tuyệt đối không được ghi trực tiếp vào mã nguồn hay biến môi trường của pipeline.
1. CI/CD runner assume một IAM role thông qua liên kết OIDC để lấy token tạm thời.
2. Các secret (như Slack webhooks hay database passwords) được lưu trữ trực tiếp trong AWS Secrets Manager.
3. ArgoCD mount các secret này vào pod trong cụm EKS thông qua External Secrets Operator tại thời điểm pod khởi chạy.

GitHub secret được giới hạn ở metadata phi đám mây cần thiết để bootstrap OIDC, không phải các khóa AWS dài hạn. Terraform nhận tên secret và ARN, không phải giá trị secret. Pipeline triển khai xác minh rằng Helm value và đầu ra Terraform không để lộ API key, webhook URL hoặc thông tin xác thực của AI Engine.

## 7. Scheduled batch deployment

State machine của Step Functions và EventBridge Scheduler được quản lý và triển khai qua các module Terraform. Quy trình deploy tuân thủ quy trình kiểm tra vận hành:

```
1. Deploy định nghĩa JSON mới của Step Functions qua Terraform.
2. Tạm thời vô hiệu hóa (disable) quy tắc EventBridge Scheduler để tránh kích hoạt pipeline giữa chừng.
3. Chạy thử nghiệm (smoke-test) để xác minh kết nối đến endpoint API và các bảng Glue.
4. Kích hoạt (enable) lại quy tắc EventBridge Scheduler để trỏ vào version state machine mới.
5. Ghi nhận thời gian cập nhật và phiên bản triển khai vào bảng DynamoDB deployment log.
```

Trình tự triển khai bộ lập lịch ngăn chặn việc các định nghĩa workflow được cập nhật một nửa xử lý một lượt chạy hàng ngày. Nếu state machine thay đổi payload gọi AI, việc triển khai cũng chạy kiểm tra tính tương thích hợp đồng AI trước khi kích hoạt lại lịch trình. Các smoke test thất bại sẽ giữ lịch trình ở trạng thái vô hiệu hóa và tạo một cảnh báo cho người vận hành với ARN state machine tốt đã biết trước đó.

## 8. Observability stack

Trạng thái vận hành và độ ổn định của hệ thống được giám sát qua bộ công cụ tập trung:

| Thành phần | Công cụ sử dụng | Mục đích giám sát |
|---|---|---|
| **Log Aggregator** | CloudWatch Logs / Container Insights | Tập trung hóa nhật ký hoạt động từ application, Lambda, và stdout của EKS containers. |
| **Trace Analyzer** | AWS X-Ray | Tracing đường đi của request từ Step Functions, qua Lambda, đến internal ALB trong EKS. |
| **Metrics Collector** | Prometheus / Managed Grafana | Theo dõi mức sử dụng CPU/Memory của EKS pods, số lượng node group, và các hành động của Karpenter. |
| **Alarms Engine** | CloudWatch Alarms | Gửi cảnh báo qua SNS nếu Step Functions gặp lỗi, hoặc dữ liệu dashboard không cập nhật (>26 giờ). |

Các báo động triển khai cốt lõi bao gồm lỗi Step Functions, tỷ lệ lỗi Lambda, endpoint nội bộ AI Engine không khả dụng, trạng thái không khỏe mạnh của node group EKS, số lượng pod pending quá mức, gián đoạn spot tăng đột biến, lỗi ghi audit và dữ liệu dashboard cũ. Việc triển khai không được coi là hoàn thành cho đến khi các báo động này hiện diện và smoke test ghi lại một bản ghi kiểm toán.

## 9. Open questions

- [ ] **ArgoCD Topology**: Nên vận hành ArgoCD theo mô hình hub-and-spoke từ tài khoản quản trị chính, hay cài đặt các thực thể ArgoCD riêng biệt trong cụm EKS của từng môi trường?
- [ ] **Grafana Integration**: Có nên chia sẻ dashboard theo dõi chỉ số hạ tầng với đội ngũ AIOps không, hay chỉ giới hạn quyền truy cập cho đội hạ tầng CDO?
- [ ] **Plan Artifact Retention**: Thời gian lưu trữ plan artifact: Plan artifact của Terraform đã xem xét nên được lưu trữ trong bao lâu để làm bằng chứng kiểm toán cho staging và prod?
- [ ] **Prod Release Branching**: Nhánh release trên prod: Các bản phát hành production nên sử dụng một nhánh `prod` được bảo vệ hay sử dụng các thẻ phát hành (release tags) của GitHub được hỗ trợ bởi phê duyệt môi trường?

## Related documents

- [`02_infra_design_vi.md`](02_infra_design_vi.md) - Cấu trúc cụm EKS, subnet mạng, và định tuyến node group.
- [`03_security_design_vi.md`](03_security_design_vi.md) - Thiết lập IRSA, danh mục secret, và network policies.
