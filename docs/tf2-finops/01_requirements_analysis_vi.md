# Phân tích Yêu cầu (Requirements Analysis) - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Final (W11 T6 Pack #1) → Refined (W12 T4 Pack #2)
-->

## 1. Context

Task Force 2 đang xây dựng hệ thống **FinOps Watch** cho CFO của một công ty quy mô trung bình (mid-size) đang chạy môi trường AWS multi-account (khoảng 80 kỹ sư chia thành 12 squad). Tháng trước, hóa đơn AWS của công ty đã tăng đột biến 2.3 lần, từ mức cơ sở (baseline) ~$180k lên ~$420k. Nguyên nhân gốc rễ là do một cụm máy chủ thử nghiệm (training cluster) bị bỏ quên trong một tài khoản non-production, tiêu tốn ~$400/ngày trong suốt 18 ngày (lãng phí khoảng ~$7k). Đội ngũ Finance đã mất gần một tuần để theo vết và phát hiện ra sự lãng phí này.

CFO mong muốn có một hệ thống **FinOps Watch** hoạt động liên tục theo chu kỳ (cadence) xác định để nạp dữ liệu chi phí (CUR và Cost Explorer API), phát hiện các bất thường (anomaly) với tỷ lệ precision và false-positive đo lường được, định tuyến cảnh báo (alert routing) đến đúng phòng ban (Finance so với Engineering), và kích hoạt các hành động ngăn chặn tự động an toàn (safe containment) đối với các mẫu lãng phí rõ ràng (ví dụ: tài nguyên nhàn rỗi, chi phí gắn sai thẻ tag, hoặc cụm training chạy quá mức kiểm soát).

Đội ngũ CDO chịu trách nhiệm về FinOps control plane, xây dựng kiến trúc lakehouse-centric để ingest và chuẩn hóa dữ liệu chi phí, quản lý workflow điều phối (orchestration), quản lý trạng thái vận hành, hiển thị dashboard, định tuyến cảnh báo, thiết lập các containment guardrails, và ghi lại nhật ký kiểm toán (audit logs). Đội ngũ CDO cũng đảm nhận việc host AI Engine (do đội ngũ AIOps cung cấp) trên AWS EKS, phân chia các workload giữa hai nhóm node group: on-demand và spot.

## 2. Infra non-functional requirements

Hệ thống CDO phải đáp ứng các yêu cầu phi chức năng (NFRs) sau đây để đảm bảo tính sẵn sàng vận hành:

| NFR | Target | Justification |
|---|---|---|
| Scheduled processing cadence | 24h default | Cân bằng giữa tần suất cập nhật dữ liệu CUR/Cost Explorer, chi phí vận hành, và khả năng kiểm soát false-positive. |
| Availability | ≥99.5% cho scheduled run workflows và dashboards | Đảm bảo hệ thống kiểm tra chi phí hoạt động liên tục và ổn định. |
| Auditability | Retention ≥90 ngày, append-only logs cho containment | Yêu cầu bắt buộc của khách hàng để phục vụ kiểm toán và truy vết. |
| Dashboard readability | Giao diện Finance-friendly, không yêu cầu kỹ năng SQL | Đội ngũ CFO phải đọc hiểu được các bất thường chi phí mà không cần chạy truy vấn kỹ thuật. |
| Cost per run | Tối thiểu hóa; theo dõi bằng `Cần bằng chứng: Chi phí vận hành pipeline CDO` | Đảm bảo bản thân hệ thống vận hành hoạt động hiệu quả về mặt chi phí. |
| Security baseline | IAM least-privilege, cross-account read-only access | Ranh giới cứng: NEVER terminate prod, delete data, hoặc modify IAM. |
| AI Engine hosting uptime | ≥99.5% availability cho hosted model API | API AI Engine do CDO host trên EKS phải đáng tin cậy cho các tác vụ gọi inference đồng bộ. |

## 3. Differentiation angle (KEY)

- **Angle chọn**: FinOps control plane dạng lakehouse-centric kết hợp serverless orchestration và CDO-hosted AI Engine trên AWS EKS.
- **Why this angle**: Quy trình FinOps trong thực tế hoạt động theo chu kỳ 24h tự nhiên theo tần suất xuất bản dữ liệu CUR. Việc nạp dữ liệu CUR và Cost Explorer API vào một lakehouse (S3 + Glue Data Catalog + Athena) cho phép lưu trữ lịch sử để truy vấn, phục vụ kiểm toán và tạo ra các materialized views thân thiện với Finance. AI Engine được triển khai trên cụm EKS chuyên biệt, sử dụng managed node groups để tối ưu hóa chi phí: các service API chạy ổn định (inference/explainer) được đặt trên on-demand nodes, trong khi các workload batch nặng (batch scoring, feature engineering, model retraining) chạy trên spot nodes. Thiết kế lai này giúp giảm thiểu chi phí máy chủ nhàn rỗi và đảm bảo khả năng mở rộng của hệ thống.
- **Trade-off chấp nhận**: Chấp nhận độ phức tạp vận hành của cụm EKS và quy trình triển khai bằng Helm/GitOps so với kiến trúc serverless container thuần túy. Điều này là xứng đáng vì EKS cung cấp khả năng kiểm soát chặt chẽ vị trí đặt workload (node affinity đối với on-demand và spot), bảo mật mạng (network policies), và mở rộng quy mô hiệu quả cho các tác vụ batch và training nặng.
- **Lock date**: 2026-06-23 (khóa thiết kế W11).

## 4. CDO vs AIOps responsibility split

Bảng phân chia trách nhiệm giữa đội CDO và AIOps được xác định cụ thể như sau:

| Nhiệm vụ | CDO | AIOps |
|---|---|---|
| Ingest cost data (CUR, Cost Explorer API) | Owns | |
| Chuẩn hóa dữ liệu cost & kiểm tra schema | Owns | |
| Xử lý tag metadata & phân định tài nguyên sở hữu | Owns | |
| Orchestration workflow (Step Functions) | Owns | |
| Quản lý run state, idempotency & scheduling | Owns | |
| Xây dựng dashboard thân thiện với Finance (QuickSight/Athena) | Owns | |
| Định tuyến cảnh báo (các kênh Finance vs. Engineering) | Owns | |
| Triển khai safe containment guardrails & audit log trail | Owns | |
| EKS Cluster Hosting Platform (Vòng đời cluster, IAM roles, VPC networking) | Owns | |
| EKS Managed Node Groups (Cấu hình On-demand/Spot) | Owns | |
| Xây dựng deployment pipelines (Helm, GitOps, IaC) cho AI workloads | Owns | |
| Cấu hình runtime monitoring & autoscaling (HPA/KEDA) | Owns | |
| AI Engine model internals, logic & code | | Owns |
| Huấn luyện model, retraining & cấu hình hyperparameter | | Owns |
| Logic tính confidence scoring & phân loại anomaly | | Owns |
| Soạn thảo văn bản giải thích (explanatory text) & tóm tắt tự nhiên | | Owns |
| Quản lý model versioning & đóng gói artifact | | Owns |
| Đánh giá và báo cáo hiệu năng backtest của AI model | | Owns |
| Cung cấp các versioned container artifacts (images, weights, configs) | | Provides |

*Ghi chú: Đội ngũ CDO tiêu thụ (consume) AI Engine thông qua một hợp đồng API được version hóa, được expose qua endpoint service nội bộ trong cụm EKS. AIOps cung cấp các container image và model weight được gắn version rõ ràng, trong khi CDO quản lý việc triển khai, vận hành, tự động scale và xử lý lỗi.*

## 5. Constraints

- **AWS only**: Không sử dụng kiến trúc multi-cloud. Toàn bộ tài nguyên phải được triển khai tại region `ap-southeast-1`.
- **Synthetic data only**: Dữ liệu hóa đơn thực tế được giả lập thông qua cơ chế inject anomaly tổng hợp trừ khi khách hàng cung cấp quyền truy cập hóa đơn thật.
- **Backtest target**: AI Engine phải đạt precision ≥80% và false-positive rate ≤10% trên bộ dữ liệu backtest 3 tháng. CDO lưu trữ các chỉ số này làm bằng chứng tích hợp hệ thống.
- **Cadence**: Chạy batch theo lịch trình mỗi 24h.
- **NEVER terminate prod, NEVER delete data, NEVER modify IAM**: Ranh giới bảo mật cứng và tuyệt đối. Nghiêm cấm mọi hành động containment tự động thực hiện trực tiếp trên tài nguyên production. Mọi tác vụ trên production chỉ giới hạn ở mức: tag, suggest, hoặc dry-run.
- **Dry-run mode**: Bắt buộc đối với toàn bộ các containment patterns trên mọi môi trường.
- **Audit trail**: Bắt buộc ghi lại nhật ký cho mọi đề xuất hoặc thực thi containment, thời gian lưu trữ tối thiểu 90 ngày.
- **Dashboard accessibility**: Bảng hiển thị trực quan được thiết kế riêng cho Finance, không yêu cầu người dùng có kiến thức SQL.
- **Code freeze**: Thứ Tư W12.

## 6. Open questions

- [ ] **AWS multi-account topology**: Số lượng tài khoản AWS chính xác cần onboard là bao nhiêu, và OIDC role trust đã được thiết lập chưa?
- [ ] **CUR export latency**: CUR 2.0 đã được cấu hình định dạng parquet và xuất partition theo giờ vào S3 bucket đích chưa?
- [ ] **Tagging compliance baseline**: Tỷ lệ tài nguyên hiện tại được tag đầy đủ các key `owner` và `squad` là bao nhiêu?
- [ ] **Escalation SLA**: Một hành động containment sẽ chờ ở trạng thái `dry-run` hoặc chờ phê duyệt trong bao lâu trước khi escalate lên quy trình duyệt manual?
- [ ] **AIOps API contract freeze**: Cấu trúc payload cho API `/detect` đã được đóng băng và freeze chưa?
- [ ] **Budget ceiling**: Hạn mức ngân sách tối đa dành cho CDO EKS hosting platform (control plane + node groups) trong thời gian chạy capstone là bao nhiêu?
- [ ] **Identity management**: Truy cập dashboard QuickSight sẽ được tích hợp với Identity Provider (IdP) doanh nghiệp qua SAML/OIDC như thế nào?
- [ ] **Spot reclamation strategy**: Điểm lưu trữ checkpoint (format và S3 location) của AIOps batch training jobs đã được xác định để xử lý khi spot node bị thu hồi chưa?
