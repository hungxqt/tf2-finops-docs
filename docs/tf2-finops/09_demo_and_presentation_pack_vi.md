# Tài liệu Demo và Thuyết trình (Demo & Presentation Pack) - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Refined (W12 T4 Pack #2)
-->

> [!IMPORTANT]
> **Ranh giới Bảo mật**: Môi trường demo và mọi kịch bản thuyết trình phải thể hiện sự tuân thủ nghiêm ngặt ranh giới bảo mật cứng: **NEVER terminate prod, delete data, hoặc modify IAM**.


## 1. Kịch bản demo (Demo script)

Kịch bản này hướng dẫn người thuyết trình cách trình diễn toàn bộ các khả năng của nền tảng FinOps Watch CDO, giả lập luồng công việc phát hiện và giảm thiểu bất thường chi phí thực tế với dữ liệu giả lập.

### Bước 1 - Chèn bất thường chi phí giả lập (Step 1 - Inject synthetic cost anomaly)
- **Hành động (Action)**: Chạy kịch bản chèn giả lập để đưa các bản ghi chi phí vào S3 raw billing bucket.
- **Thông số kỹ thuật Telemetry (Telemetry Specifications)**: Dữ liệu đo lường hiệu năng là CUR-only (S3 CUR partition pulls và Cost Explorer API calls). Nó loại bỏ hoàn toàn mọi dữ liệu hiệu năng từ CloudWatch (các tín hiệu hiệu suất sử dụng như CPUUtilization, DatabaseConnections, hoặc memory_mib) nhằm giúp việc phát hiện bất thường của AI Engine tập trung hoàn toàn vào chi phí. Các chỉ số CloudWatch chỉ được sử dụng riêng biệt bởi nền tảng CDO cho mục đích giám sát vận hành (operational observability).
- **Payload**: Một lô các bản ghi EC2 giả lập hiển thị mức tăng chi phí đột ngột gấp 10 lần trên một cụm instance GPU không được quản lý (ví dụ: chi tiêu 500 USD cho EC2 g5.4xlarge).
- **Xác minh (Verification)**: Kiểm tra đường dẫn tệp S3 raw zone: `s3://cdo-raw-cost-bucket/exports/year=2026/month=06/`.

### Bước 2 - Kích hoạt bộ lập lịch pipeline (Step 2 - Trigger pipeline scheduler)
- **Hành động (Action)**: Kích hoạt thủ công quy tắc EventBridge Scheduler hoặc chạy lệnh kích hoạt qua AWS CLI.
- **Lệnh CLI (CLI Command)**: `aws stepfunctions start-execution --state-machine-arn <State_Machine_ARN> --input "{\"Date\": \"2026-06-24\"}"` (sử dụng trình bọc rtk).
- **Xác minh (Verification)**: Bảng điều khiển Step Functions hiển thị trạng thái màu xanh "Running".

### Bước 3 - Gọi endpoint AI Engine dùng chung (Step 3 - Invoke shared AI Engine endpoint - POST /v1/detect)
- **Hành động (Action)**: Giám sát luồng công việc Step Functions thu thập dữ liệu khi nó đạt đến trạng thái chấm điểm AI (AI scoring state).
- **Hành động nội bộ (Internal Action)**: Luồng công việc Step Functions thực hiện cuộc gọi HTTP POST đến Private REST API Gateway endpoint của AI Engine tại `/v1/detect` sử dụng xác thực IAM SigV4.
- **Request Headers tiêu chuẩn**:
  - `X-Tenant-Id`: Xác định bên thuê (ví dụ: `CDO-01`).
  - `X-Idempotency-Key`: Khóa kết hợp format `tenant_id:YYYY-MM-DD` (ví dụ: `CDO-01:2026-06-24`).
  - `X-Correlation-Id`: UUID theo dõi luồng thực thi.
  - `X-Payload-SHA256`: Mã băm SHA256 của payload yêu cầu để kiểm tra tính toàn vẹn.
  - `X-Request-Timestamp`: Nhãn thời gian định dạng ISO 8601.
- **Payload yêu cầu**:
  - Schema URL: `telemetry://finops-watch/v3`.
  - Ingestion Type: `RAW_JSON` cho truy vấn Cost Explorer API (<10MB) hoặc `S3_POINTER` cho dữ liệu CUR trong S3 (<500MB).
  - Control Flags: `is_ad_hoc` (bỏ qua kiểm tra idempotency 24h cho các quét khẩn cấp), `is_estimated` (chi tiêu ước tính từ CE, làm giảm độ tin cậy và bỏ qua tự động containment), `is_forced_dry_run` (nếu độ hoàn thiện dữ liệu telemetry < 0.8, bắt buộc chạy chế độ dry-run).
  - Dữ liệu Telemetry: Chỉ bao gồm các thuộc tính chi phí và metadata, loại bỏ hoàn toàn các chỉ số hiệu năng CloudWatch.
- **Xác minh (Verification)**: Kiểm tra nhật ký thực thi Lambda để tìm phản hồi HTTP `202 Accepted` với body JSON chứa:
  - `audit_id` (UUID theo dõi)
  - `status`: `"processing"`
  - `retry_after_seconds`: `30`

### Bước 4 - Lấy kết quả bằng Polling (GET /v1/detect/result/{audit_id}) & Thực thi tác vụ container AI Engine (Step 4 - Poll results & Execute AI Engine task)
- **Hành động (Action)**: Thực hiện gọi định kỳ lấy kết quả (polling) từ endpoint `GET /v1/detect/result/{audit_id}` qua Private API Gateway sau mỗi 30 giây.
- **Hành động nội bộ (Internal Action)**: AI Engine chạy trên hạ tầng AWS Lambda container functions xử lý payload thu thập dữ liệu. SQS lưu đệm các request; hàm Worker Lambda container thực thi chấm điểm mô hình AI, đánh giá điểm độ tin cậy bất thường và tổng hợp chi tiết RCA, ghi nhận kết quả vào DynamoDB. Khi hoàn thành, yêu cầu polling trả về HTTP `200 OK`.
- **Payload phản hồi**:
  - `audit_id`: Khớp với UUID thực thi.
  - `anomalies_list`: Mảng các bất thường phát hiện được cùng điểm tin cậy và giải thích chi tiết.
  - `pagination`: Đối tượng phân trang chứa `next_token` và `limit`.
- **Xác minh & Biện pháp an toàn (Verification & Fail-safes)**:
  - Nếu phát hiện trùng lặp khóa idempotency, API trả về HTTP `409` với header `Retry-After: 30`.
  - Nếu gửi khóa trùng lặp nhưng payload khác nhau, API trả về HTTP `400` với mã lỗi `ERR_IDEMPOTENCY_MISMATCH`.
  - Nếu Bedrock bị quá thời hạn phản hồi (giới hạn cứng Bedrock Bedrock API 45 giây, trả về `ERR_LLM_TIMEOUT`) hoặc dịch vụ bị dừng (`ERR_SERVICE_DOWN`), pipeline lập tức kích hoạt rules engine tĩnh và cảnh báo đội ngũ SRE.
  - Kiểm tra bảng bản ghi bất thường DynamoDB để xác minh bản ghi mới được ghi nhận với chuỗi liên kết kiểm toán mã hóa (cryptographic audit trail chain) tính toán theo công thức `sha256(current_payload + previous_hash)`.

### Bước 5 - Cập nhật bảng điều khiển CDO (Step 5 - Update CDO dashboard)
- **Hành động (Action)**: Lambda tổng hợp dữ liệu được kích hoạt để xây dựng lại các tài nguyên bảng điều khiển.
- **Hành động nội bộ (Internal Action)**: Các dữ liệu tổng hợp được biên dịch thành các tệp S3 JSON tĩnh, và một invalidation bộ nhớ đệm CloudFront được thực thi.
- **Xác minh (Verification)**: Mở URL bảng điều khiển trong trình duyệt và xác minh rằng biểu đồ chi tiêu hàng ngày hiển thị điểm bất thường chi phí được phủ lên.

### Bước 6 - Định tuyến cảnh báo (Step 6 - Route alerts)
- **Hành động (Action)**: Kiểm tra các kênh thông báo.
- **Hành động nội bộ (Internal Action)**: Alert Routing Lambda kiểm tra mức độ nghiêm trọng của bất thường và các tag sở hữu của squad.
- **Xác minh (Verification)**: 
  - Slack: Xác minh rằng một tin nhắn thông báo đã đến kênh `#squad-prediction-models` chứa ARN tài nguyên, chi phí chênh lệch và liên kết bảng điều khiển.
  - SES/SNS: Xác minh rằng danh sách gửi thư của Finance đã nhận được email tóm tắt về đột biến chi phí.

### Bước 7 - Thực thi containment ở chế độ giả lập và kiểm soát thời gian đếm ngược (Step 7 - Execute dry-run containment and countdown control)
- **Hành động (Action)**: Kiểm tra nhật ký kiểm toán containment và các kiểm soát đếm ngược.
- **Hành động nội bộ (Internal Action)**: Containment engine thực thi kiểm tra chính sách trên tài nguyên mục tiêu. Vì tài nguyên nằm dưới quy tắc sản xuất (production), engine sẽ thực thi ở chế độ dry-run (Giá trị An toàn: `Never` - không bao giờ tự động áp dụng containment trên production). Đối với môi trường dev/sandbox, engine có thể áp dụng containment (Giá trị An toàn: `After countdown` hoặc `Yes with policy approval`). Quản trị viên có thể hoãn/snooze thời gian đếm ngược bằng cách gọi endpoint `POST /v1/action/extend`.
- **Xác minh (Verification)**: Xác minh rằng instance EC2 AWS mục tiêu vẫn đang chạy, nhưng bảng nhật ký kiểm toán DynamoDB có một bản ghi mới hiển thị hành động được đề xuất `stop_instance` với `execution_mode: dry-run`.

### Bước 8 - Thực thi giả lập hoàn tác (Step 8 - Execute rollback simulation - POST /v1/action/rollback)
- **Hành động (Action)**: Khôi phục trạng thái containment giả lập từ giao diện bảng điều khiển hoặc API.
- **Hành động nội bộ (Internal Action)**: Quản trị viên nhấp vào nút "Revert" trên bảng điều khiển CDO, hành động này sẽ gọi endpoint `POST /v1/action/rollback` để thực thi các bước rollback được xác định trong bản ghi kiểm toán (ví dụ: khôi phục trạng thái tag ban đầu).
- **Xác minh (Verification)**: Kiểm tra nhật ký CLI và các bản ghi DynamoDB để xác nhận trạng thái kiểm toán thay đổi thành `RollbackCompleted`.

---

## 2. Danh sách bằng chứng (Evidence checklist)

Danh sách này phác thảo các tệp nhật ký, bảng cơ sở dữ liệu và thông tin liên lạc cụ thể cần thiết để xác minh tính thực thi thành công của pipeline nền tảng CDO trong các buổi kiểm toán.

- **Các tệp nhật ký CUR trong S3 (CUR logs in S3)**: Các tệp thu thập dữ liệu được lưu trữ dưới `s3://cdo-raw-cost-bucket/exports/` xác nhận khả năng tương thích định dạng dữ liệu thô.
- **Xác minh VPC Flow Logs & IAM SigV4**: Nhật ký cho thấy log thực thi của Private REST API Gateway và lưu lượng qua VPC Endpoint với chữ ký yêu cầu SigV4 và không có lưu lượng thoát ra internet.
- **Các bản ghi DynamoDB (DynamoDB records)**:
  - Bảng anomalies: Bản ghi chứa `anomaly_id`, `confidence_score` và `explanation` từ AI Engine, cùng với các tham số phân trang.
  - Bảng audit trail: Bản ghi chứa đầy đủ 14 trường hành động containment, xác minh `correlation_id` khớp với luồng thực thi Step Functions, và chứa một khối liên kết kiểm toán mã hóa tính theo công thức `sha256(current_payload + previous_hash)`.
- **Các webhook của Slack (Slack webhooks)**: Nhật ký webhook từ kênh ứng dụng Slack mục tiêu, xác nhận việc gửi payload JSON chính xác mà không để lộ cấu trúc chi phí thô.
- **Ảnh chụp màn hình QuickSight / Bảng điều khiển (QuickSight / Dashboard screenshots)**: Các tham chiếu hình ảnh độ phân giải cao hiển thị:
  - Xu hướng chi tiêu hàng ngày với điểm bất thường được đánh dấu phủ lên.
  - Danh sách containment đang hoạt động chi tiết hóa nhãn chế độ dry-run (Giá trị An toàn: `Never` cho production, `After countdown` hoặc `Yes with policy approval` cho dev/sandbox).
- **Nhật ký tag CLI (CLI tag logs)**: Nhật ký API CloudTrail xác nhận các cuộc gọi API `ec2:CreateTags` ở chế độ dry-run khớp với ARN instance mục tiêu.

---

## 3. Các điểm thuyết phục của CDO (CDO pitch points)

Các điểm bán hàng chính của kiến trúc data lakehouse tập trung vào hồ dữ liệu serverless cho kiểm soát FinOps:

- **Tiết kiệm chi phí nhờ mô hình Serverless (Serverless cost savings)**: Bằng cách chọn S3, Glue và Athena cho data lakehouse, nền tảng hoạt động với chi phí cực thấp so với các cơ sở dữ liệu luôn chạy truyền thống (RDS/Redshift). Chi phí tính toán chỉ phát sinh trong cửa sổ thực thi truy vấn, mang lại mức tiết kiệm lên tới 90% cho các hoạt động xử lý hàng loạt hàng ngày.
- **Tối ưu hóa hosting AI dùng chung (Shared AI hosting optimization)**: Việc triển khai các endpoint AI Engine dùng chung phía sau Private REST API Gateway host trên các hàm AWS Lambda container giúp tối ưu hóa dung lượng tính toán giữa nhiều nền tảng CDO (loại bỏ chi phí nhàn rỗi của ECS/ALB) trong khi vẫn giữ cách ly khối lượng công việc thông qua header `X-Tenant-Id` và Resource Policy của API Gateway.
- **Tuân thủ đầy đủ (Complete compliance)**: Nhật ký kiểm toán hai lớp (DynamoDB cho tốc độ giao diện người dùng và S3 với Object Lock cho tính không thể sửa đổi) đảm bảo rằng tất cả các hành động tự động và được đề xuất được bảo tồn trong ít nhất 90 ngày, đáp ứng các quy định kiểm toán tài chính. Mỗi mục nhật ký kiểm toán được liên kết mã hóa bằng `sha256(current_payload + previous_hash)` để chống giả mạo.
- **Vận hành không rủi ro (Risk-free operation)**: Các cấu hình mặc định dry-run nghiêm ngặt trong môi trường sản xuất (production) và chạy thử (staging) giúp ngăn ngừa việc gián đoạn dịch vụ ngoài ý muốn. Tự động hóa được giới hạn một cách an sau trong môi trường non-production/sandbox nơi các chính sách được thực thi nghiêm ngặt.
- **Cách ly đa người thuê (Multi-tenant isolation)**: Các tiền tố S3 có cấu trúc và phân vùng Glue tách biệt dữ liệu chi phí theo tài khoản và squad. Truy cập chéo tài khoản dựa trên các chính sách IAM assume-role chỉ đọc, ngăn chặn các di chuyển ngang không được phép.

---

## 4. Phản hồi các câu hỏi hóc búa (Curveball responses)

Các lập luận kiến trúc cho các câu hỏi thử thách phổ biến:

- **Làm thế nào để xử lý độ trễ xuất dữ liệu CUR của AWS (lên tới 24 giờ)? (How do you handle AWS CUR data export lag?)**
  - *Phản hồi*: Mặc dù các bản xuất CUR có độ trễ cố định, chu kỳ lập lịch 24 giờ của chúng tôi (ADR-001) được thiết kế để căn chỉnh với chu kỳ này. Để thu hẹp khoảng cách cho các cảnh báo thời gian thực quan trọng, data plane của chúng tôi kết hợp các bản xuất CUR với các cuộc gọi hàng ngày đến AWS Cost Explorer API, nơi cung cấp các dữ liệu tổng hợp chi phí có độ trễ thấp hơn.
- **Làm thế nào để xử lý các cảnh báo giả của AI Engine (mở rộng quy mô bình thường bị phân loại là bất thường)? (How do you handle AI Engine false positives?)**
  - *Phản hồi*: Tư thế containment ưu tiên an toàn của chúng tôi (ADR-005) đảm bảo rằng không có hành động hủy hoại tự động nào được thực hiện trên các tài nguyên sản xuất. Hơn nữa, các squad kỹ thuật nhận được cảnh báo Slack kèm theo nút "Snooze", hành động này gọi API endpoint `POST /v1/action/extend` để hoãn/snooze thời gian đếm ngược, cho phép họ đánh dấu phân loại đó là mở rộng quy mô bình thường và ngăn chặn các kích hoạt containment tiếp theo cho tài nguyên đó. Ngoài ra, dữ liệu telemetry thu thập hoàn toàn là CUR-only và không gửi bất kỳ chỉ số hiệu năng CloudWatch nào (như CPU, Memory, hoặc DatabaseConnections) tới AI Engine để phát hiện bất thường, giữ cho data plane luôn nhẹ nhàng và tuân thủ.
- **Điều gì xảy ra nếu một lỗi phần mềm kích hoạt containment tự động trên các tài nguyên sản xuất? (What happens if a bug triggers automated containment on production assets?)**
  - *Phản hồi*: Containment trong môi trường sản xuất được khóa cứng ở chế độ dry-run ở cả cấp chính sách IAM và cấp thời gian chạy (runtime) của Lambda (Giá trị An toàn: `Never`). Ngay cả trong trường hợp hỏng cơ sở dữ liệu hoặc lỗi mã nguồn, các vai trò IAM được gán cho Lambda thực thi containment không sở hữu các quyền cần thiết để xóa, hủy hoặc tắt các tài nguyên sản xuất.
- **Nền tảng xử lý tình trạng throttling API của AWS Cost Explorer như thế nào trong quá trình mở rộng quy mô? (How does the platform handle AWS Cost Explorer API throttling during scaling?)**
  - *Phản hồi*: Lambda thu thập dữ liệu tích hợp cơ chế thử lại với exponential backoff. Ngoài ra, kết quả truy vấn được lưu vào bộ nhớ đệm cục bộ trong S3 trong suốt thời gian chạy để ngăn các yêu cầu API trùng lặp cho cùng một khoảng ngày.
- **Điều gì xảy ra nếu bảng điều khiển bị mất đồng bộ với các tài nguyên AWS thực tế? (What happens if the dashboard becomes out-of-sync with actual AWS resources?)**
  - *Phản hồi*: Các tài nguyên tĩnh của bảng điều khiển được cập nhật ngay lập tức vào cuối mỗi lần chạy pipeline. Một invalidation CloudFront được kích hoạt bằng lập trình để xóa các bộ nhớ đệm ở cạnh. Một nút "Sync Now" cũng được cung cấp trên giao diện để truy vấn trực tiếp các bản ghi DynamoDB.
- **Bảo mật hoàn tác được thực thi như thế nào để ngăn chặn các thay đổi tài nguyên trái phép? (How is rollback security enforced to prevent unauthorized resource changes?)**
  - *Phản hồi*: Việc thực thi hoàn tác gọi endpoint API `POST /v1/action/rollback`. Nó yêu cầu các quyền IAM và xác minh MFA tương tự. Mỗi yêu cầu rollback phải được gắn với một ID sự cố hoặc change ticket hợp lệ, và hành động này được ghi nhật ký đầy đủ vào nhật ký kiểm toán WORM trong S3.
- **Ai sở hữu triển khai và vòng đời vận hành Lambda container của AI Engine dùng chung? (Who owns the Lambda container deployment and operational lifecycle of the shared AI Engine?)**
  - *Phản hồi*: CDO sở hữu việc triển khai hạ tầng host (VPC, subnets, Private REST API Gateway, giới hạn concurrency, role execution, queues, và DynamoDB state stores) để đảm bảo tính sẵn sàng, bảo mật của hệ thống và xác thực SigV4. AIOps sở hữu logic mô hình AI, logic RCA/khuyến nghị, thực thi rules engine dự phòng cục bộ, tuân thủ hợp đồng API nội bộ, và build container image.
- **Điều gì xảy ra nếu AI Engine gặp lỗi, quá thời gian phản hồi, hoặc nhận được các yêu cầu trùng lặp? (What happens if the AI Engine fails, times out, or receives duplicate requests?)**
  - *Phản hồi*: Nếu AI Engine phát hiện các khóa idempotency trùng lặp, nó trả về HTTP `409` kèm theo header `Retry-After: 30`, hoặc trả về HTTP `400` với mã lỗi `ERR_IDEMPOTENCY_MISMATCH` nếu các payload khác nhau. Nếu Bedrock bị hết thời gian chờ (giới hạn cứng 45s của Bedrock Bedrock API, trả về `ERR_LLM_TIMEOUT`) hoặc dịch vụ bị lỗi (`ERR_SERVICE_DOWN`), pipeline CDO sẽ lập tức chuyển sang thực thi rules engine tĩnh và kích hoạt cảnh báo SRE, đảm bảo một trạng thái containment an toàn tuyệt đối.

---

## 5. Câu hỏi mở (Open questions)

- [ ] **Bảo mật tích hợp Slack Webhook (Slack Webhook Integration Security)**: Chúng ta có nên chuyển đổi từ Slack incoming webhooks tĩnh sang một ứng dụng Slack an toàn sử dụng các mã thông báo OAuth của AWS Secrets Manager để tăng kiểm soát định tuyến không?
- [ ] **Tên miền tùy chỉnh cho Cognito OIDC (Cognito OIDC Custom Domain)**: Nhóm Finance có yêu cầu xác thực người dùng AWS Cognito OIDC tích hợp đăng nhập một lần (SSO) để truy cập bảng điều khiển không?
- [ ] **Giới hạn truy vấn Athena (Athena Query Limits)**: Giới hạn cứng nào nên được cấu hình cho việc sử dụng dữ liệu truy vấn Athena mỗi ngày để ngăn chặn hóa đơn tăng đột biến do phân tích tự do?
- [ ] **Ngân sách Token cho mô hình Bedrock (Bedrock Model Token Budget)**: Giới hạn token nào nên được thiết lập cho mỗi tenant trong cấu hình Secrets Manager để tránh chi phí Bedrock vượt trội khi gặp số lượng lớn bất thường chi phí đột biến? (`Cần bằng chứng: đo kiểm chi phí Bedrock/token theo baseline thực tế`)
