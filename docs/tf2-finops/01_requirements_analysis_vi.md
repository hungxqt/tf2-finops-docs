# Phân tích Yêu cầu (Requirements Analysis) - Task Force 2 · FinOps Watch<!-- Doc owner: CDO Team
     Status: Final (W11 T6 Pack #1) -> Refined (W12 T4 Pack #2)
-->

## 1. Context

Task Force 2 đang xây dựng hệ thống **FinOps Watch** cho CFO của một công ty quy mô trung bình (mid-size) đang chạy môi trường AWS multi-account (khoảng 80 kỹ sư chia thành 12 squad). Tháng trước, hóa đơn AWS của công ty đã tăng đột biến 2.3 lần, từ mức cơ sở (baseline) ~$180k lên ~$420k. Nguyên nhân gốc rễ là do một cụm máy chủ thử nghiệm (training cluster) bị bỏ quên trong một tài khoản non-production, tiêu tốn ~$400/ngày trong suốt 18 ngày (lãng phí khoảng ~$7k). Đội ngũ Finance đã mất gần một tuần để theo vết và phát hiện ra sự lãng phí này.

CFO mong muốn có một hệ thống **FinOps Watch** hoạt động liên tục theo chu kỳ (cadence) xác định để nạp dữ liệu chi phí (CUR và Cost Explorer API), phát hiện các bất thường (anomaly) với tỷ lệ precision và false-positive đo lường được, định tuyến cảnh báo (alert routing) đến đúng phòng ban (Finance so với Engineering), và kích hoạt các hành động ngăn chặn tự động an toàn (safe containment) đối với các mẫu lãng phí rõ ràng (ví dụ: tài nguyên nhàn rỗi, chi phí gắn sai thẻ tag, hoặc cụm training chạy quá mức kiểm soát).

Đội ngũ CDO chịu trách nhiệm về FinOps control plane, xây dựng kiến trúc lakehouse-centric để ingest và xử lý dữ liệu chi phí (S3 CUR partition pulls và Cost Explorer API calls), workflow điều phối (orchestration), quản lý trạng thái vận hành, hiển thị dashboard, định tuyến cảnh báo (alert routing), thiết lập các containment guardrails, và ghi nhật ký kiểm toán (audit logs). Đội ngũ CDO cũng triển khai và vận hành hạ tầng host ECS (VPC, subnets, ALB, tasks sizing, auto scaling, security groups, task IAM roles, queues, và DynamoDB state stores) cho một endpoint AI Engine của Task Force dùng chung trên ECS Fargate (cluster 'tf-2-aiops-cluster'), được truy cập bởi cả CDO-01 và CDO-02 qua `https://ai-engine.tf-2.internal/` với xác thực IAM SigV4. Các workload được phân chia giữa các Fargate always-on capacity provider tasks và Fargate Spot capacity provider tasks. AIOps sở hữu logic mô hình AI, logic RCA/khuyến nghị, logic fallback, quản lý hợp đồng, build container image, và duy trì baseline đánh giá.

Đội ngũ AIOps sở hữu bất kỳ bộ dữ liệu lịch sử tổng hợp (synthetic historical dataset) nào được sử dụng để huấn luyện, cải tiến, hiệu chuẩn hoặc backtest mô hình phát hiện bất thường. Tài liệu CDO coi bộ dữ liệu đó là đầu vào phục vụ chất lượng mô hình ở thượng nguồn (upstream), chứ không phải là nguồn định cỡ hệ thống (sizing source) hoặc nguồn dữ liệu vận hành của nền tảng CDO. CDO tiêu thụ mô hình thông qua một hợp đồng API đã ký kết, gửi dữ liệu chi phí CUR-only (loại bỏ hoàn toàn telemetry hiệu năng CloudWatch như CPUUtilization, DatabaseConnections, memory_mib vốn chỉ dùng cho giám sát vận hành của CDO), lưu trữ bằng chứng quyết định được trả về và chứng minh rằng chính sách cảnh báo và containment được áp dụng một cách an toàn.

Đối với các bên liên quan thuộc bộ phận Finance, thành công có nghĩa là dashboard có thể trả lời bốn câu hỏi mà không cần kiến thức SQL: cái gì đã thay đổi, tài khoản hoặc squad nào sở hữu nó, nền tảng tin cậy đến mức nào và hành động nào được cho phép. Đối với những người đánh giá CDO, thành công có nghĩa là mỗi lần chạy theo lịch trình đều có một cửa sổ nhập liệu (input window) có thể truy vết, idempotency key, phiên bản hợp đồng AI Engine, quyết định cảnh báo, chế độ containment và hồ sơ kiểm toán (audit record).

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
| AI Engine hosting uptime | ≥99.5% availability cho hosted model API | API AI Engine do CDO host trên ECS phải đáng tin cậy cho các tác vụ gọi inference đồng bộ. |
| Cost data contract coverage | Dữ liệu chi phí CUR-only (account, service, region, resource, tag, cost period, USD amount, và estimated/final flag); loại bỏ các metric hiệu năng CloudWatch (CPU, memory, database connections) khi phát hiện bất thường | Đảm bảo CDO gửi đủ ngữ cảnh vận hành tới AIOps AI Engine mà không cần sở hữu dữ liệu huấn luyện mô hình. Các metric hiệu năng chỉ được sử dụng cho giám sát vận hành CDO (cảnh báo, logging, dashboard). |
| Idempotency | Một lần chạy được chấp nhận cho mỗi tài khoản và cửa sổ chi phí (cost window) | Ngăn ngừa cảnh báo trùng lặp, các cuộc gọi AI Engine trùng lặp và double-counted (tính toán lặp lại) khi cập nhật dashboard. |
| Alert explainability | Mỗi cảnh báo bất thường bao gồm độ tin cậy (confidence), mức độ nghiêm trọng (severity), cửa sổ bằng chứng (evidence window), định tuyến chủ sở hữu và giải thích | Finance và Engineering phải có thể quyết định xem cảnh báo có hợp lệ hay không và cần làm gì tiếp theo. |
| Containment safety | Prod bị giới hạn ở tag, gợi ý (suggest) hoặc dry-run; các hành động trên non-prod yêu cầu phê duyệt chính sách | Giữ cho tự động hóa hữu ích mà không vượt qua ranh giới cứng của khách hàng. |

Các NFRs được cố ý viết dưới dạng các mục tiêu vận hành, không chỉ là các ưu tiên về mặt kiến trúc. Nền tảng CDO chỉ có thể vượt qua capstone nếu chứng minh được rằng workflow hàng ngày đã chạy, AI Engine được gọi thông qua hợp đồng đã thống nhất, đầu ra của mô hình được xác thực trước khi sử dụng và mọi hành động được đề xuất đều có thể kiểm toán trong ít nhất 90 ngày.

## 3. Differentiation angle (KEY)

- **Angle chọn**: FinOps control plane dạng lakehouse-centric kết hợp serverless orchestration và CDO-hosted AI Engine trên AWS ECS (cụ thể trong ECS cluster 'tf-2-aiops-cluster').
- **Why this angle**: Quy trình FinOps trong thực tế hoạt động theo chu kỳ 24h tự nhiên theo tần suất xuất bản dữ liệu CUR. Việc nạp dữ liệu CUR và Cost Explorer API vào một lakehouse (S3 + Glue Data Catalog + Athena) cho phép lưu trữ lịch sử để truy vấn, phục vụ kiểm toán và tạo ra các materialized views thân thiện với Finance. AI Engine được triển khai trên cụm ECS chuyên biệt (tf-2-aiops-cluster), sử dụng Fargate Capacity Providers để tối ưu hóa chi phí: các service API chạy ổn định (inference/explainer) được đặt trên Fargate always-on capacity provider tasks, trong khi các workload batch nặng (batch scoring, feature engineering, model retraining) chạy trên Fargate Spot capacity provider tasks. Thiết kế lai này giúp giảm thiểu chi phí máy chủ nhàn rỗi và đảm bảo khả năng mở rộng của hệ thống.
- **Trade-off chấp nhận**: Chấp nhận độ phức tạp vận hành của cụm ECS và quy trình triển khai bằng Terraform ECS configuration và GitHub Actions (CI/CD) deployment pipelines so với kiến trúc serverless container thuần túy. Điều này là xứng đáng vì ECS cung cấp khả năng kiểm soát chặt chẽ vị trí đặt workload (always-on vs. Spot capacity provider allocation), bảo mật mạng (security groups), và mở rộng quy mô hiệu quả cho các tác vụ batch và training nặng.
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
| ECS Cluster Hosting Platform (Vòng đời cluster, ECS Task Role, ECS Task Execution Role, VPC networking) | Owns | |
| ECS Fargate Capacity Providers (Cấu hình always-on/Spot) | Owns | |
| Xây dựng deployment pipelines (Terraform ECS configuration, GitHub Actions (CI/CD) deployment pipelines, IaC) cho AI workloads | Owns | |
| Cấu hình runtime monitoring & autoscaling (ECS Service Auto Scaling (using CPU target tracking 70% and SQS step scaling)) | Owns | |
| AI Engine model internals, logic & code | | Owns |
| Huấn luyện model, retraining & cấu hình hyperparameter | | Owns |
| Logic tính confidence scoring & phân loại anomaly | | Owns |
| Soạn thảo văn bản giải thích (explanatory text) & tóm tắt tự nhiên | | Owns |
| Quản lý model versioning & đóng gói artifact | | Owns |
| Đánh giá và báo cáo hiệu năng backtest của AI model | | Owns |
| Cung cấp các versioned container artifacts (images, weights, configs) | | Provides |

*Ghi chú: Đội ngũ CDO tiêu thụ (consume) AI Engine thông qua một endpoint AI Engine của Task Force dùng chung trên ECS Fargate, được truy cập bởi cả CDO-01 và CDO-02 qua `https://ai-engine.tf-2.internal/` với xác thực IAM SigV4. Ranh giới trách nhiệm được xác định cụ thể: CDO sở hữu và triển khai hạ tầng host (VPC, subnets, ALB, tasks sizing, auto scaling, security groups, task IAM roles, queues, và DynamoDB state stores), trong khi AIOps sở hữu logic mô hình AI, logic RCA/khuyến nghị, logic fallback, quản lý hợp đồng, build container image, và duy trì baseline đánh giá. Telemetry gửi tới AI Engine chỉ gồm dữ liệu chi phí CUR và Cost Explorer API, loại bỏ hoàn toàn các chỉ số hiệu năng CloudWatch (CPU, memory, database connections) vốn chỉ dành riêng cho việc giám sát vận hành của CDO.*

Ranh giới này được thực thi tại thời điểm chạy (runtime) cũng như trong tài liệu. CDO xác thực schema yêu cầu và phản hồi `/v1/detect` trước mỗi bản phát hành tương thích, ghi lại phiên bản mô hình do AIOps trả về, lưu trữ URI bằng chứng cho mỗi bất thường và fail closed (đóng an toàn) khi AI Engine không khả dụng hoặc trả về payload không hợp lệ. AIOps tiếp tục chịu trách nhiệm về các chỉ số chất lượng mô hình như precision, recall, hiệu chuẩn độ tin cậy và logic giải thích, trong khi CDO tiếp tục chịu trách nhiệm về việc liệu các đầu ra đó có được sử dụng an toàn trong các quy trình cảnh báo, dashboard và containment hay không.

Đầu ra quyết định tối thiểu của AI mà CDO tiêu thụ là: `run_id`, `model_version`, `anomaly_id`, `tenant/account`, `anomaly_type`, `confidence`, `severity`, `expected_spend`, `actual_spend`, `delta`, `evidence_window`, `explanation`, `recommended_route`, `recommended_containment_mode` và `evidence_uri`. Việc thiếu các trường bắt buộc sẽ chặn containment và tạo ra cảnh báo cho người vận hành.

### 4.1 Tuân thủ Hợp đồng Mục tiêu Mức độ Dịch vụ (SLO)

Nền tảng CDO tiêu thụ AI Engine API theo các Mục tiêu Mức độ Dịch vụ (SLOs) được xác định trong `ai-api-contract.md` §6. Sự tích hợp phải được xác minh và giám sát chặt chẽ dựa trên các mục tiêu bắt buộc sau:

| Chỉ số SLO | Mục tiêu Hợp đồng | Sự kiện xác minh |
|---|---|---|
| **Độ trễ Ingestion (P99)** | < 50 ms | Thời gian xử lý hai chiều của yêu cầu POST `/v1/detect`. |
| **Độ trễ truy vấn kết quả (P99)** | < 10 ms | Thời gian truy xuất dữ liệu từ DynamoDB Store. |
| **LLM Inference SLA** | < 30 giây | Khung thời gian thực thi của Amazon Bedrock (Nova LLM) và ghi DB. |
| **Tính khả dụng hệ thống** | >=99.5% | Tổng thời gian hoạt động của ALB nội bộ/API Gateway dành cho CDO. |
| **Tỷ lệ lỗi** | < 0.5% | Tỷ lệ phản hồi lỗi hệ thống (HTTP 5xx) trên tổng số yêu cầu. |

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
- [ ] **Budget ceiling**: Hạn mức ngân sách tối đa dành cho CDO ECS hosting platform (control plane + Fargate capacity provider tasks) trong thời gian chạy capstone là bao nhiêu?
- [ ] **Identity management**: Truy cập dashboard S3 + CloudFront sẽ được tích hợp với Identity Provider (IdP) doanh nghiệp (ví dụ sử dụng CloudFront + Cognito hoặc OIDC) như thế nào, và khi nào nên đưa QuickSight vào làm tích hợp BI trong tương lai?
- [ ] **Spot reclamation strategy**: Điểm lưu trữ checkpoint (format và S3 location) của AIOps batch training jobs đã được xác định để xử lý khi Fargate Spot task bị thu hồi chưa?
- [ ] **False-positive approval calendar**: Lịch phê duyệt false-positive: Finance có thể cung cấp các cửa sổ di dời hệ thống (migration), load-test và flash-sale đã biết cho AIOps để hiệu chuẩn mô hình và cho CDO để chú thích cảnh báo không?
- [ ] **Dashboard decision owner**: Chủ sở hữu quyết định dashboard: Vai trò Finance nào ký duyệt các nhãn mức độ nghiêm trọng (severity labels), ngưỡng ngân sách và từ ngữ leo thang được sử dụng trong các chế độ hiển thị dành cho ban điều hành?
- [ ] **Containment approval owner**: Chủ sở hữu phê duyệt containment: Đối với các hành động ở chế độ apply trên non-prod, sự phê duyệt đến từ chủ sở hữu squad, chủ sở hữu nền tảng hay chủ sở hữu Finance?
- [ ] **Evidence retention format**: Định dạng lưu trữ bằng chứng: Bằng chứng dài hạn chỉ nên được lưu giữ dưới dạng các đối tượng S3 có thể truy vấn bằng Athena, hay được nhân bản vào các bản ghi DynamoDB đã được materialized để tăng tốc độ dashboard?
