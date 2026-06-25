# Phân tích Yêu cầu (Requirements Analysis) - Task Force 2 · FinOps Watch
<!-- Doc owner: CDO Team
     Status: Final (W11 T6 Pack #1) -> Refined (W12 T4 Pack #2)
-->

## 1. Context

Task Force 2 đang xây dựng hệ thống **FinOps Watch** cho CFO của một công ty quy mô trung bình (mid-size) đang chạy môi trường AWS multi-account (khoảng 80 kỹ sư chia thành 12 squad). Tháng trước, hóa đơn AWS của công ty đã tăng đột biến 2.3 lần, từ mức cơ sở (baseline) ~$180k lên ~$420k. Nguyên nhân gốc rễ là do một cụm máy chủ thử nghiệm (training cluster) bị bỏ quên trong một tài khoản non-production, tiêu tốn ~$400/ngày trong suốt 18 ngày (lãng phí khoảng ~$7k). Đội ngũ Finance đã mất gần một tuần để theo vết và phát hiện ra sự lãng phí này.

CFO mong muốn có một hệ thống **FinOps Watch** hoạt động liên tục theo chu kỳ (cadence) xác định để nạp dữ liệu chi phí (CUR và Cost Explorer API), phát hiện các bất thường (anomaly) với tỷ lệ precision và false-positive đo lường được, định tuyến cảnh báo (alert routing) đến đúng phòng ban (Finance so với Engineering), và kích hoạt các hành động ngăn chặn tự động an toàn (safe containment) đối với các mẫu lãng phí rõ ràng (ví dụ: tài nguyên nhàn rỗi, chi phí gắn sai thẻ tag, hoặc cụm training chạy quá mức kiểm soát).

Đội ngũ CDO chịu trách nhiệm về FinOps control plane, xây trúc lakehouse-centric để ingest và xử lý dữ liệu chi phí (S3 CUR partition pulls và Cost Explorer API calls) cùng với các chỉ số hiệu năng (resource utilization metrics) từ CloudWatch, workflow điều phối (orchestration), quản lý trạng thái vận hành, hiển thị dashboard, định tuyến cảnh báo (alert routing), thiết lập các containment guardrails, và ghi nhật ký kiểm toán (audit logs). Đội ngũ CDO cũng triển khai và vận hành hạ tầng host Lambda container (VPC, subnets, các hàm Lambda, execution roles, reserved concurrency, kho lưu trữ idempotency dựa trên DynamoDB, và nhật ký kiểm toán dựa trên S3) để chạy AI Engine do AIOps cung cấp. Trong workflow chạy batch theo lịch trình mặc định, bộ điều phối trung tâm Step Functions điều phối luồng xử lý bằng cách gọi `/v1/detect` để bắt đầu phát hiện bất thường đồng bộ, gọi `/v1/decide` để tạo báo cáo nguyên nhân gốc rễ (RCA) và kế hoạch hành động dry-run, và gọi `/v1/verify` để xác thực kết quả can thiệp. Việc rollback thủ công hoặc theo chính sách được kích hoạt qua `/v1/audit/{audit_id}/rollback`, trong khi `/v1/status/{id}` được dùng để kiểm tra trạng thái can thiệp hoặc tự phục hồi (không phải polling phát hiện). Lưu ý rằng các endpoint này đại diện cho ngữ nghĩa hợp đồng logic (logical contract semantics) cho việc tích hợp mô hình, không phải các đường dẫn REST/HTTP vật lý được triển khai thực tế, do không triển khai API Gateway vật lý trong luồng batch cơ sở. Các workload được chạy dưới dạng thực thi container image serverless trên AWS Lambda, và SQS/DLQ chỉ được sử dụng cho hàng đợi retry của alert routing chứ không nằm trong luồng phát hiện. AIOps sở hữu container image AI Engine tương thích với Lambda, mã nguồn mô hình, logic phát hiện, văn bản giải thích và các chỉ số đánh giá backtest.

Đội ngũ AIOps sở hữu bất kỳ bộ dữ liệu lịch sử tổng hợp (synthetic historical dataset) nào được sử dụng để huấn luyện, cải tiến, hiệu chuẩn hoặc backtest mô hình phát hiện bất thường. Tài liệu CDO coi bộ dữ liệu đó là đầu vào phục vụ chất lượng mô hình ở thượng nguồn (upstream), chứ không phải là nguồn định cỡ hệ thống (sizing source) hoặc nguồn dữ liệu vận hành của nền tảng CDO. CDO tiêu thụ mô hình thông qua một hợp đồng API đã ký kết, gửi dữ liệu chi phí CUR và Cost Explorer kết hợp với `resource_utilization_metrics` từ CloudWatch (CPU, memory, network, disk, database connections, và GPU metrics để phát hiện tài nguyên nhàn rỗi hoặc cụm training chạy quá mức), lưu trữ bằng chứng quyết định được trả về và chứng minh rằng chính sách cảnh báo và containment được áp dụng một cách an toàn.

Đối với các bên liên quan thuộc bộ phận Finance, thành công có nghĩa là dashboard có thể trả lời bốn câu hỏi mà không cần kiến thức SQL: cái gì đã thay đổi, tài khoản hoặc squad nào sở hữu nó, nền tảng tin cậy đến mức nào và hành động nào được cho phép. Đối với những người đánh giá CDO, thành công có nghĩa là mỗi lần chạy theo lịch trình đều có một cửa sổ nhập liệu (input window) có thể truy vết, idempotency key, phiên bản hợp đồng AI Engine, quyết định cảnh báo, chế độ containment và hồ sơ kiểm toán (audit record).

### 1.1 Ánh xạ Hợp đồng Lập trình (Programmatic Contract Mapping v1.3.0)

Để tích hợp với các hợp đồng phát hiện bất thường dùng chung, nền tảng CDO này ánh xạ các giao diện logic với các thành phần thực thi Lambda serverless như sau:

| Endpoint / Giao diện | Hợp đồng Nguồn | Thiết kế & Triển khai Mục tiêu của CDO |
|---|---|---|
| `POST /v1/detect` | `ai-api-contract.md` | Bắt đầu phát hiện bất thường theo lô đồng bộ. CDO gọi endpoint riêng tư `/v1/detect` của AI Engine qua ALB nội bộ mặc định bằng dữ liệu chi phí CUR (hoặc dữ liệu daily của Cost Explorer khi chế độ fallback `telemetry_delay_event = true` được kích hoạt), trả về `success`, `correlation_id`, `anomalies_detected`, `anomalies_list`, và `data_confidence` (HIGH/LOW). Hỗ trợ tùy chọn `callback_url` để gửi thông báo callback bổ sung (không thay thế phản hồi đồng bộ). |
| `GET /v1/status/{id}` | `ai-api-contract.md` | Lấy trạng thái can thiệp/tự phục hồi cho anomaly_id hoặc audit_id cụ thể. (Không còn dùng để polling trạng thái phát hiện). |
| `POST /v1/decide` | `ai-api-contract.md` | Yêu cầu RCA, khuyến nghị hành động, và CLI dry-run payload. CDO ánh xạ các payload Finance (chỉ đọc) và Engineering (kế hoạch hành động/can thiệp) riêng biệt. |
| `POST /v1/verify` | `ai-api-contract.md` | Đánh giá hiệu quả can thiệp bằng các metric sau hành động. Kích hoạt khóa containment nếu error budget bị tiêu hao > 1%. |
| `POST /v1/audit/{audit_id}/rollback` | `ai-api-contract.md` | Bộ xử lý rollback thủ công hoặc theo chính sách. Khôi phục trạng thái tài nguyên và cập nhật error budget của tenant. |
| `resource_utilization_metrics` | `telemetry-contract.md` | Đầu vào hỗn hợp gồm chi phí và hiệu năng bao gồm CPU (dưới dạng mảng `cpu_utilization_hourly` thô mỗi 24 giờ; AI Engine tự tính toán số giờ idle liên tục), memory, net, disk, database connections, và GPU metrics. Tự động chuyển sang chế độ CUR-only (data_confidence: LOW, chỉ dry-run/alert) khi thiếu metric CloudWatch. |
| Bảo mật Ingress & Định danh | `telemetry-contract.md` | Chữ ký được xác thực qua AWS IAM SigV4 (`Authorization`), kiểm tra toàn vẹn payload (`X-Payload-SHA256`), cô lập người thuê (`X-Tenant-Id`), chống replay attack với độ lệch clock skew < 300s (`X-Request-Timestamp`), và khóa chống trùng lặp (`X-Idempotency-Key`). |
| Triển khai Per-CDO | `deployment-contract.md` | AI engine được cung cấp dưới dạng ECR container image. CDO tự triển khai endpoint riêng trên AWS Lambda Container, cô lập theo ngữ cảnh tenant, và được kiểm soát bằng các cảnh báo Bedrock/budget limit. |

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
| AI Engine hosting uptime | ≥99.5% availability cho các hàm hosted model | Hàm Lambda container AI Engine do CDO host đằng sau Application Load Balancer (ALB) nội bộ phải đáng tin cậy cho các tác vụ gọi thực thi HTTPS nội bộ bảo mật. |
| Cost data contract coverage | CUR + Cost Explorer + CloudWatch resource_utilization_metrics (cpu_percent, memory_mib, network_in_bytes, network_out_bytes, disk_io_ops, database_connections, gpu_utilization, cpu_utilization_hourly) | Đảm bảo CDO gửi thông tin chi phí cùng với các metric hiệu năng từ CloudWatch phục vụ phát hiện bất thường (hỗ trợ phát hiện idle_resource và runaway_usage), tự động fallback sang CUR-only (data_confidence: LOW) khi thiếu metric. |
| Idempotency | Một lần chạy được chấp nhận cho mỗi tài khoản và cửa sổ chi phí (cost window) | Ngăn ngừa cảnh báo trùng lặp, các cuộc gọi AI Engine trùng lặp và double-counted (tính toán lặp lại) khi cập nhật dashboard. |
| Alert explainability | Mỗi cảnh báo bất thường bao gồm độ tin cậy (confidence), mức độ nghiêm trọng (severity), cửa sổ bằng chứng (evidence window), định tuyến chủ sở hữu và giải thích | Finance và Engineering phải có thể quyết định xem cảnh báo có hợp lệ hay không và cần làm gì tiếp theo. |
| Containment safety | Prod bị giới hạn ở tag, gợi ý (suggest) hoặc dry-run; các hành động trên non-prod yêu cầu phê duyệt chính sách | Giữ cho tự động hóa hữu ích mà không vượt qua ranh giới cứng của khách hàng. |

Các NFRs được cố ý viết dưới dạng các mục tiêu vận hành, không chỉ là các ưu tiên về mặt kiến trúc. Nền tảng CDO chỉ có thể vượt qua capstone nếu chứng minh được rằng workflow hàng ngày đã chạy, AI Engine được gọi thông qua hợp đồng đã thống nhất, đầu ra của mô hình được xác thực trước khi sử dụng và mọi hành động được đề xuất đều có thể kiểm toán trong ít nhất 90 ngày.

## 3. Differentiation angle (KEY)

- **Angle chọn**: FinOps control plane dạng lakehouse-centric kết hợp serverless orchestration và CDO-hosted AI Engine trên các AWS Lambda container images.
- **Why this angle**: Quy trình FinOps trong thực tế hoạt động theo chu kỳ 24h tự nhiên theo tần suất xuất bản dữ liệu CUR. Việc nạp dữ liệu CUR và Cost Explorer API vào một lakehouse (S3 + Glue Data Catalog + Athena) cho phép lưu trữ lịch sử để truy vấn, phục vụ kiểm toán và tạo ra các materialized views thân thiện với Finance. AI Engine được host dưới dạng một Lambda container image được triển khai qua ECR đằng sau một Application Load Balancer (ALB) nội bộ. Để tối ưu hóa chi phí và giảm thiểu độ phức tạp vận hành, hệ thống sử dụng compute serverless (không có chi phí cluster nhàn rỗi), hàng đợi SQS/DLQ cho việc đệm retry gửi alert, gửi các yêu cầu HTTPS nội bộ đến target group của ALB để thực thi, và Lambda reserved concurrency làm cơ chế bảo vệ mặc định (với Provisioned Concurrency là tùy chọn tối ưu hóa production nếu độ trễ khởi động lạnh yêu cầu). Cách tiếp cận endpoint mạng nội bộ riêng tư này giảm thiểu tối đa chi phí chạy cố định đồng thời đảm bảo truy cập nội bộ an toàn.
- **Trade-off chấp nhận**: Chấp nhận độ trễ khởi động lạnh (cold-start) của các hàm Lambda container image (thường từ 1-5 giây khi nạp và khởi tạo container) so với các máy chủ luôn chạy. Điều này là chấp nhận được vì chu kỳ 24h không yêu cầu thời gian phản hồi API đồng bộ dưới một giây, và việc thực thi đồng bộ yêu cầu AI Engine Lambda hoàn thành trong giới hạn timeout của Lambda, giúp loại bỏ sự phức tạp của việc polling trạng thái.
- **Lock date**: 2026-06-23 (khóa thiết kế W11).

Sự khác biệt không phải là "sử dụng AI cho FinOps"; quyền sở hữu đó thuộc về AIOps. Sự khác biệt của CDO là control plane xung quanh quyết định của AI: kéo dữ liệu lặp lại, bằng chứng lịch sử có thể truy vấn, gọi mô hình được gắn phiên bản (versioned model invocation), định tuyến an toàn, containment thực thi theo chính sách và báo cáo tài chính trực quan. Một cách tiếp cận thuần túy tập trung vào dashboard sẽ chỉ hiển thị chi tiêu mà không thể khép kín quy trình. Một cách tiếp cận thuần túy tập trung vào tự động hóa sẽ hoạt động quá quyết liệt mà không có đủ bằng chứng. Góc độ được chọn giữ cho vòng lặp FinOps hàng ngày có thể đo lường và đảo ngược được.

Hợp đồng tích hợp củng cố góc độ này. CDO chuẩn hóa dữ liệu đầu vào thanh toán AWS trước khi gọi AI Engine, duy trì việc gọi mô hình có phiên bản và ghi lại đủ bằng chứng để Finance và Engineering hiểu được đường dẫn quyết định. AIOps có thể độc lập cải tiến mô hình, trong khi CDO giữ cho vòng lặp vận hành luôn ổn định.

## 4. CDO vs AIOps responsibility split

Bảng phân chia trách nhiệm giữa đội CDO và AIOps được xác định cụ thể như sau:

| Nhiệm vụ | CDO | AIOps |
|---|---|---|
| Ingest cost data (CUR, Cost Explorer API) | Owns | |
| Chuẩn hóa dữ liệu cost & kiểm tra schema | Owns | |
| Xử lý tag metadata & phân định tài nguyên sở hữu | Owns | |
| Orchestration workflow (Step Functions) | Owns | |
| Quản lý run state, idempotency & scheduling | Owns | |
| Xây dựng dashboard thân thiện với Finance (S3 + CloudFront dashboard backed by Athena/DynamoDB summaries) | Owns | |
| Định tuyến cảnh báo (các kênh Finance vs. Engineering) | Owns | |
| Triển khai safe containment guardrails & audit log trail | Owns | |
| Nền tảng Lambda Container host AI Engine (Tích hợp VPC, Execution Roles, Reserved Concurrency) | Owns | |
| Kiểm soát concurrency của Lambda (Reserved / Provisioned Concurrency, cấu hình SQS/DLQ) | Owns | |
| Xây dựng deployment pipelines (ECR image digest pinning, định tuyến Lambda alias, IaC) cho AI workloads | Owns | |
| Giám sát runtime & kiểm soát concurrency (Lambda reserved concurrency, CloudWatch logs, và X-Ray) | Owns | |
| AI Engine model internals, logic & code | | Owns |
| Huấn luyện model, retraining & cấu hình hyperparameter | | Owns |
| Logic tính confidence scoring & phân loại anomaly | | Owns |
| Soạn thảo văn bản giải thích (explanatory text) & tóm tắt tự nhiên | | Owns |
| Quản lý model versioning & đóng gói artifact | | Owns |
| Đánh giá và báo cáo hiệu năng backtest của AI model | | Owns |
| Cung cấp các versioned container artifacts (images, weights, configs) | | Provides |

*Ghi chú: Đội ngũ CDO tiêu thụ (consume) AI Engine thông qua một hợp đồng lập trình có phiên bản (ai-api-contract.md v1.4.0) qua các yêu cầu HTTPS riêng tư tới target group của ALB (đại diện cho các endpoint logic `/v1/detect`, `/v1/status/{id}`, `/v1/decide`, `/v1/verify` và `/v1/audit/{audit_id}/rollback`) với xác thực AWS SigV4. Ranh giới trách nhiệm được xác định cụ thể: CDO sở hữu và triển khai hạ tầng host (VPC, subnets, ALB nội bộ, hàm Lambda container, execution roles, reserved concurrency, các hàng đợi SQS cho alert, kho lưu trữ idempotency dựa trên DynamoDB `finops-idempotency-{env}`, và cache rollback dựa trên DynamoDB `finops-rollback-cache`), trong khi AIOps sở hữu container image AI Engine tương thích với Lambda, mã nguồn mô hình, logic phát hiện, văn bản giải thích và các chỉ số đánh giá backtest. Telemetry bao gồm CUR, Cost Explorer, và các chỉ số hiệu năng `resource_utilization_metrics` từ CloudWatch (CPU, memory, network, disk, database connections, và GPU metrics), tự động chuyển sang chế độ CUR-only (data_confidence: LOW) nếu CloudWatch không khả dụng.*

*Ghi chú về Ngôn ngữ Hợp đồng (Contract Wording)*: Các hợp đồng đã ký (`deployment-contract.md` v1.3.0, `ai-api-contract.md` v1.4.0) giả định cấu hình triển khai Task Force chung (có thể đề cập đến ECS Fargate, App Runner hoặc Lambda). Nền tảng CDO này ánh xạ ECR container image do AIOps cung cấp sang AWS Lambda Container hosting đằng sau ALB nội bộ. Các tài liệu hợp đồng cũ/chung được coi là tài liệu tham chiếu, nhưng front-end ALB nội bộ tuân thủ đúng các endpoint HTTP `/v1/*` của hợp đồng.

Ranh giới này được thực thi tại thời điểm chạy (runtime) cũng như trong tài liệu. CDO xác thực schema yêu cầu và phản hồi `/v1/detect` trước mỗi bản phát hành tương thích, ghi lại phiên bản mô hình do AIOps trả về, lưu trữ URI bằng chứng cho mỗi bất thường và fail closed (đóng an toàn) khi AI Engine không khả dụng hoặc trả về payload không hợp lệ. AIOps tiếp tục chịu trách nhiệm về các chỉ số chất lượng mô hình như precision, recall, hiệu chuẩn độ tin cậy và logic giải thích, trong khi CDO tiếp tục chịu trách nhiệm về việc liệu các đầu ra đó có được sử dụng an toàn trong các quy trình cảnh báo, dashboard và containment hay không.

Đầu ra quyết định tối thiểu của AI mà CDO tiêu thụ là: `run_id`, `model_version`, `anomaly_id`, `tenant/account`, `anomaly_type`, `confidence`, `severity`, `expected_spend`, `actual_spend`, `delta`, `evidence_window`, `explanation`, `recommended_route`, `recommended_containment_mode` và `evidence_uri`. Việc thiếu các trường bắt buộc sẽ chặn containment và tạo ra cảnh báo cho người vận hành.

### 4.1 Tuân thủ Hợp đồng Mục tiêu Mức độ Dịch vụ (SLO)

Nền tảng CDO tiêu thụ AI Engine API theo các Mục tiêu Mức độ Dịch vụ (SLOs) được xác định trong `ai-api-contract.md` §6. Sự tích hợp phải được xác minh và giám sát chặt chẽ dựa trên các mục tiêu bắt buộc sau:
Nền tảng CDO tiêu thụ AI Engine theo các Mục tiêu Mức độ Dịch vụ (SLOs) được xác định trong `ai-api-contract.md` §6. Sự tích hợp phải được xác minh và giám sát chặt chẽ dựa trên các mục tiêu bắt buộc sau:

| Chỉ số SLO | Mục tiêu Hợp đồng | Sự kiện xác minh |
|---|---|---|
| **Độ trễ P99 `/v1/detect`** | < 300 ms | Thời gian xử lý hai chiều của yêu cầu POST `/v1/detect` đo tại CloudWatch. |
| **Độ trễ P99 `/v1/decide`** | < 500 ms | Thời gian xử lý yêu cầu `/v1/decide`. |
| **Độ trễ P99 `/v1/verify`** | < 500 ms | Thời gian xử lý yêu cầu `/v1/verify`. |
| **LLM Inference SLA** | < 30 giây | Khung thời gian thực thi của Amazon Bedrock (Nova LLM) và ghi DB. |
| **Tính khả dụng hệ thống** | >=99.5% | Tính khả dụng toàn bộ của các endpoint API HTTPS ALB riêng tư. |
| **Tỷ lệ lỗi (5xx)** | < 0.5% | Tỷ lệ phản hồi lỗi 5xx trên tổng số yêu cầu gọi hàm. |

Bất kỳ vi phạm nào đối với các tham số SLA này sẽ kích hoạt quy trình dự phòng (cảnh báo SRE, áp dụng quy tắc tĩnh, hoặc đóng an toàn đối với các quyết định containment).

## 5. Constraints

- **AWS only**: Không sử dụng kiến trúc multi-cloud. Toàn bộ tài nguyên phải được triển khai tại region `ap-southeast-1`.
- **Dữ liệu mô hình tổng hợp do AIOps sở hữu**: Các bộ dữ liệu tổng hợp lịch sử được sử dụng để huấn luyện, nâng cao hoặc backtest mô hình đều thuộc sở hữu của AIOps. CDO có thể tham chiếu các chỉ số do AIOps cung cấp, nhưng không được tuyên bố quyền sở hữu đối với bộ dữ liệu của mô hình.
- **Backtest target**: AI Engine phải đạt precision ≥80% và false-positive rate ≤10% trên bộ dữ liệu backtest 3 tháng. CDO lưu trữ các chỉ số này làm bằng chứng tích hợp hệ thống.
- **Cadence**: Chạy batch theo lịch trình mỗi 24h.
- **NEVER terminate prod, NEVER delete data, NEVER modify IAM**: Ranh giới bảo mật cứng và tuyệt đối. Nghiêm cấm mọi hành động containment tự động thực hiện trực tiếp trên tài nguyên production. Mọi tác vụ trên production chỉ giới hạn ở mức: tag, suggest, hoặc dry-run.
- **Dry-run mode**: Bắt buộc đối với toàn bộ các containment patterns trên mọi môi trường.
- **Audit trail**: Bắt buộc ghi lại nhật ký cho mọi đề xuất hoặc thực thi containment, thời gian lưu trữ tối thiểu 90 ngày.
- **Dashboard accessibility**: Bảng hiển thị trực quan được thiết kế riêng cho Finance, không yêu cầu người dùng có kiến thức SQL.
- **Code freeze**: Thứ Tư W12.
- **Dữ liệu demo CDO**: CDO có thể sử dụng các lệnh inject anomaly tổng hợp chỉ dành cho smoke test tích hợp, demo dashboard và dry-run containment. Các sự kiện demo này không phải là bằng chứng huấn luyện AI.
- **Vùng triển khai**: Mục tiêu triển khai chính là `ap-southeast-1`.
- **Phạm vi containment**: Ít nhất một đường dẫn containment cho non-prod có thể được triển khai, nhưng containment trên prod vẫn chỉ giới hạn ở tag/suggest/dry-run bất kể độ tin cậy của bất thường là bao nhiêu.
- **Tính trung thực trong đo lường**: Chi phí chạy chưa đo lường, độ trễ dashboard, độ trễ gửi cảnh báo, độ trễ inference của AI và kết quả precision thực tế phải được đánh dấu là `Cần bằng chứng: ...` cho đến khi nhóm thu thập được bằng chứng thực tế.

Các ràng buộc này xác định những gì nền tảng CDO không được phép làm. Hệ thống được phép phát hiện, giải thích, định tuyến, tag, gợi ý và giả lập containment. Nó không được phép trở thành một bot dọn dẹp không giới hạn, một đường truyền rò rỉ dữ liệu thanh toán hoặc một công cụ tự động hóa IAM.

## 6. Open questions

- [ ] **AWS multi-account topology**: Số lượng tài khoản AWS chính xác cần onboard là bao nhiêu, và OIDC role trust đã được thiết lập chưa?
- [ ] **CUR export latency**: CUR 2.0 đã được cấu hình định dạng parquet và xuất partition theo giờ vào S3 bucket đích chưa?
- [ ] **Tagging compliance baseline**: Tỷ lệ tài nguyên hiện tại được tag đầy đủ các key `owner` và `squad` là bao nhiêu?
- [ ] **Escalation SLA**: Một hành động containment sẽ chờ ở trạng thái `dry-run` hoặc chờ phê duyệt trong bao lâu trước khi escalate lên quy trình duyệt manual?
- [ ] **AIOps API contract freeze**: Cấu trúc payload cho API `/v1/detect` đã được đóng băng và freeze chưa?
- [ ] **Budget ceiling**: Hạn mức ngân sách tối đa dành cho CDO Lambda container hosting platform (thời gian chạy của Lambda, hàng đợi SQS/DLQ, và các tùy chọn Provisioned Concurrency) trong thời gian chạy capstone là bao nhiêu?
- [ ] **Identity management**: Truy cập dashboard S3 + CloudFront sẽ được tích hợp với Identity Provider (IdP) doanh nghiệp (ví dụ sử dụng CloudFront + Cognito hoặc OIDC) như thế nào, và khi nào nên đưa QuickSight vào làm tích hợp BI trong tương lai?
- [ ] **Model retraining deployment**: Tần suất AIOps huấn luyện lại mô hình là bao nhiêu, và các digest hình ảnh mới được thông báo cho CDO như thế nào để triển khai trong ECR và ghim digest Lambda?
- [ ] **False-positive approval calendar**: Lịch phê duyệt false-positive: Finance có thể cung cấp các cửa sổ di dời hệ thống (migration), load-test và flash-sale đã biết cho AIOps để hiệu chuẩn mô hình và cho CDO để chú thích cảnh báo không?
- [ ] **Dashboard decision owner**: Chủ sở hữu quyết định dashboard: Vai trò Finance nào ký duyệt các nhãn mức độ nghiêm trọng (severity labels), ngưỡng ngân sách và từ ngữ leo thang được sử dụng trong các chế độ hiển thị dành cho ban điều hành?
- [ ] **Containment approval owner**: Chủ sở hữu phê duyệt containment: Đối với các hành động ở chế độ apply trên non-prod, sự phê duyệt đến từ chủ sở hữu squad, chủ sở hữu nền tảng hay chủ sở hữu Finance?
- [ ] **Evidence retention format**: Định dạng lưu trữ bằng chứng: Bằng chứng dài hạn chỉ nên được lưu giữ dưới dạng các đối tượng S3 có thể truy vấn bằng Athena, hay được nhân bản vào các bản ghi DynamoDB đã được materialized để tăng tốc độ dashboard?
