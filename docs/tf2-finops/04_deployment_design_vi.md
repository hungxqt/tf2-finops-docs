# Thiết kế Triển khai và CI/CD (Deployment & CI/CD Design) - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Final (W11 T6 Pack #1) → Updated (W12 T4 Pack #2)
-->

## 1. IaC strategy

### 1.1 Tool choice

CDO platform sử dụng chiến lược triển khai hai lớp để phân tách rõ ràng giữa việc thiết lập hạ tầng và việc triển khai các ứng dụng chạy trên đó.
1. **Lớp hạ tầng (AWS Resources)**: Sử dụng **Terraform (v1.5+)** để khởi tạo các tài nguyên bất biến (VPC, EKS cluster, node groups, DynamoDB, S3, IAM roles).
2. **Lớp ứng dụng (Kubernetes & Applications)**: Sử dụng **Helm (v3)** và **GitOps (ArgoCD)** đối với các trạng thái ứng dụng trong cụm EKS, và cơ chế đóng gói tệp zip tiêu chuẩn để triển khai cho các hàm Lambda.

### 1.2 Module structure

Cấu trúc thư mục mã nguồn được phân chia rõ ràng giữa các modules định nghĩa tài nguyên và cấu hình môi trường cụ thể:
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

- **Quản lý file State**: File state của Terraform được lưu trữ bảo mật trong một bucket S3 tập trung, được cấu hình mã hóa phía máy chủ (`AES256`) và bật tính năng versioning.
- **State Locking**: Cơ chế khóa file state được quản lý qua một bảng DynamoDB (`cdo-tflock-table`) nhằm ngăn chặn việc chạy đồng thời nhiều tác vụ IaC.
- **Phê duyệt triển khai**: Các plan thay đổi được xuất tự động trên PR (`plan-on-PR`) và chỉ được apply khi code được merge (`apply-on-merge`) sau khi đã có sự phê duyệt từ senior reviewer.

## 2. CI/CD pipeline

### 2.1 Pipeline stages

Pipeline triển khai được tự động hóa qua GitHub Actions. Quy trình gồm các bước kiểm tra cú pháp, quét bảo mật, chạy thử Terraform, triển khai staging và cổng phê duyệt manual trước khi lên production:

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
| Triển khai Staging | Terraform / ArgoCD | Triển khai hạ tầng lên tài khoản staging; ArgoCD đồng bộ Helm charts vào EKS. | Trạng thái Pod trong EKS đạt `Running`; 100% tài nguyên đồng bộ. |
| Chạy thử Staging | Kịch bản Python riêng | Inject một cost record thử nghiệm để kiểm tra luồng định tuyến alert end-to-end. | Cảnh báo được gửi thành công về kênh Slack test. |
| Manual Approval Gate | GitHub Environment Gate | Tạm dừng pipeline lên production, chờ phê duyệt thủ công từ CDO Lead. | Chữ ký phê duyệt từ reviewer được chỉ định. |
| Triển khai Prod | Terraform / ArgoCD | Cập nhật hạ tầng và các workload EKS trên môi trường production. | Quá trình áp dụng hoàn thành không có lỗi. |
| Chạy thử Prod | Kịch bản Python riêng | Chạy thử nghiệm các tác vụ containment ở chế độ dry-run. | Nhật ký kiểm toán dry-run được ghi nhận thành công. |

### 2.2 Branch strategy

- `feature/*`: Các nhánh làm việc riêng cho từng tính năng. Target PR: `develop`.
- `develop`: Nhánh chạy chính cho môi trường staging. Tự động trigger triển khai lên tài khoản AWS Staging mỗi khi có push mới.
- `main`: Nhánh chạy chính cho môi trường production. Việc merge code từ `develop` vào `main` sẽ chạy kiểm thử staging trước khi dừng lại chờ phê duyệt thủ công để lên production.

## 3. Deployment gates

### 3.1 Security scans

Bên cạnh việc quét mã nguồn tĩnh, các kho lưu trữ ECR được bật cấu hình **Scan on Push**. Mọi image do AIOps đẩy lên sẽ được tự động quét lỗi bảo mật. Việc deploy lên EKS sẽ bị chặn lại nếu image chứa các lỗ hổng bảo mật nghiêm trọng. Pipeline CI/CD xác thực với tài khoản AWS thông qua giao thức **OpenID Connect (OIDC)**, loại bỏ việc lưu trữ cố định các AWS Access Keys trên GitHub.

### 3.2 Destructive-change review

Bất kỳ Terraform plan nào hiển thị cảnh báo thay đổi index tài nguyên hoặc có hành động xóa/khởi tạo lại (như tạo lại S3 bucket hoặc thay đổi IAM role) sẽ được gắn nhãn cảnh báo trong PR. Các thay đổi này bắt buộc phải có sự xác nhận thủ công và phê duyệt kép (dual approvals) từ CDO Lead và Security Lead.

### 3.3 AI contract compatibility

Trước khi cập nhật container trong EKS, pipeline sẽ khởi chạy một tập lệnh kiểm tra độ tương thích:
1. Đối chiếu model version đăng ký từ AIOps với cấu hình EKS hiện tại.
2. Kiểm tra JSON schema của API contract đầu vào và đầu ra tại endpoint `/detect` của AI Engine.
3. Nếu schema không tương thích, quá trình build sẽ bị dừng ngay lập tức trước khi tác động vào cụm Kubernetes, đảm bảo tính nhất quán của hệ thống.

## 4. Deployment strategy

### 4.1 Strategy

- **EKS API Workloads**: Sử dụng chiến lược **Rolling Updates** với cấu hình max surge `25%` và max unavailable `0%`. Điều này đảm bảo các pod chạy ổn định (`ai-engine-api`) luôn có replica mới sẵn sàng trước khi thu hồi các pod cũ.
- **EKS Batch Workers**: Các Kubernetes Jobs thực thi động. Các cập nhật về cấu hình worker sẽ áp dụng cho các lượt gọi job tiếp theo mà không làm ảnh hưởng đến các job đang chạy.
- **Lambda Functions**: Triển khai theo cơ chế **Weighted Aliases**. Traffic được chuyển dịch dần dần: chạy thử nghiệm canary `10%` traffic trong 5 phút, và tự động chuyển sang `100%` nếu không phát sinh lỗi.
- **Spot Node Draining**: Sử dụng Karpenter để xử lý ngắt spot nodes. Khi có tín hiệu ngắt từ EC2, Karpenter sẽ phát tín hiệu trục xuất (evict) pod để drain các pod worker một cách an toàn. Nếu một job batch scoring đang chạy bị dừng giữa chừng, orchestrator sẽ tự động phát hiện và chạy lại ở node healthy khác.

### 4.2 Rollback method

- **Rollback chính**: Thực hiện qua ArgoCD. Việc hoàn tác (revert) một commit Git về SHA ổn định trước đó sẽ tự động kích hoạt ArgoCD đồng bộ lại cấu hình trong cụm EKS trong vòng 60 giây.
- **Rollback phụ**: Đối với các hàm Lambda, workflow Step Functions sẽ bắt các mã lỗi gọi function và ngay lập tức chuyển trọng số (weight) của Lambda alias về phiên bản ổn định trước đó (RTO < 10 giây).

## 5. Environment separation

Hạ tầng được cô lập hoàn toàn trên ba tài khoản AWS độc lập:

| Môi trường (Env) | Mục đích sử dụng | Tài khoản AWS | Auto-deploy |
|---|---|---|---|
| **Sandbox** | Lập trình viên chạy thử nghiệm cục bộ và kiểm tra định dạng dữ liệu synthetic. | `1111-2222-3333` | Có (khi push lên PR) |
| **Staging** | Kiểm thử tích hợp container artifact từ AIOps và chạy toàn trình Step Functions E2E pipeline. | `4444-5555-6666` | Có (khi merge vào `develop`) |
| **Prod** | Control plane chạy chính thức. Giám sát chi phí toàn công ty. Các hành động containment bắt buộc chạy ở chế độ dry-run. | `7777-8888-9999` | Không (yêu cầu phê duyệt manual) |

## 6. Secrets in pipeline

Secrets tuyệt đối không được ghi trực tiếp vào mã nguồn hay biến môi trường của pipeline.
1. CI/CD runner assume một IAM role thông qua liên kết OIDC để lấy token tạm thời.
2. Các secret (như Slack webhooks hay database passwords) được lưu trữ trực tiếp trong AWS Secrets Manager.
3. ArgoCD mount các secret này vào pod trong cụm EKS thông qua External Secrets Operator tại thời điểm pod khởi chạy.

## 7. Scheduled batch deployment

State machine của Step Functions và EventBridge Scheduler được quản lý và triển khai qua các module Terraform. Quy trình deploy tuân thủ quy trình kiểm tra vận hành:

```
1. Deploy định nghĩa JSON mới của Step Functions qua Terraform.
2. Tạm thời vô hiệu hóa (disable) quy tắc EventBridge Scheduler để tránh kích hoạt pipeline giữa chừng.
3. Chạy thử nghiệm (smoke-test) để xác minh kết nối đến endpoint API và các bảng Glue.
4. Kích hoạt (enable) lại quy tắc EventBridge Scheduler để trỏ vào version state machine mới.
5. Ghi nhận thời gian cập nhật và phiên bản triển khai vào bảng DynamoDB deployment log.
```

## 8. Observability stack

Trạng thái vận hành và độ ổn định của hệ thống được giám sát qua bộ công cụ tập trung:

| Thành phần | Công cụ sử dụng | Mục đích giám sát |
|---|---|---|
| **Log Aggregator** | CloudWatch Logs / Container Insights | Tập trung hóa nhật ký hoạt động từ application, Lambda, và stdout của EKS containers. |
| **Trace Analyzer** | AWS X-Ray | Tracing đường đi của request từ Step Functions, qua Lambda, đến internal ALB trong EKS. |
| **Metrics Collector** | Prometheus / Managed Grafana | Theo dõi mức sử dụng CPU/Memory của EKS pods, số lượng node group, và các hành động của Karpenter. |
| **Alarms Engine** | CloudWatch Alarms | Gửi cảnh báo qua SNS nếu Step Functions gặp lỗi, hoặc dữ liệu dashboard không cập nhật (>26 giờ). |

## 9. Open questions

- [ ] **ArgoCD Topology**: Nên vận hành ArgoCD theo mô hình hub-and-spoke từ tài khoản quản trị chính, hay cài đặt các thực thể ArgoCD riêng biệt trong cụm EKS của từng môi trường?
- [ ] **Grafana Integration**: Có nên chia sẻ dashboard theo dõi chỉ số hạ tầng với đội ngũ AIOps không, hay chỉ giới hạn quyền truy cập cho đội hạ tầng CDO?

## Related documents

- [`02_infra_design_vi.md`](02_infra_design_vi.md) - Cấu trúc cụm EKS, subnet mạng, và định tuyến node group.
- [`03_security_design_vi.md`](03_security_design_vi.md) - Thiết lập IRSA, danh mục secret, và network policies.
