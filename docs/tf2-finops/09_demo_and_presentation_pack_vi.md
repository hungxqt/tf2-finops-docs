# Tài liệu Demo và Thuyết trình (Demo & Presentation Pack) - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Refined (W12 T4 Pack #2)
-->

## 1. Kịch bản demo (Demo script)

Kịch bản này hướng dẫn người thuyết trình cách trình diễn toàn bộ các khả năng của nền tảng FinOps Watch CDO, giả lập luồng công việc phát hiện và giảm thiểu bất thường chi phí thực tế với dữ liệu giả lập.

### Bước 1 - Chèn bất thường chi phí giả lập (Step 1 - Inject synthetic cost anomaly)
- **Hành động (Action)**: Chạy kịch bản chèn giả lập để đưa các bản ghi chi phí vào S3 raw billing bucket.
- **Payload**: Một lô các bản ghi EC2 giả lập hiển thị mức tăng chi phí đột ngột gấp 10 lần trên một cụm instance GPU không được quản lý (ví dụ: chi tiêu 500 USD cho EC2 g5.4xlarge).
- **Xác minh (Verification)**: Kiểm tra đường dẫn tệp S3 raw zone: `s3://cdo-raw-cost-bucket/exports/year=2026/month=06/`.

### Bước 2 - Kích hoạt bộ lập lịch pipeline (Step 2 - Trigger pipeline scheduler)
- **Hành động (Action)**: Kích hoạt thủ công quy tắc EventBridge Scheduler hoặc chạy lệnh kích hoạt qua AWS CLI.
- **Lệnh CLI (CLI Command)**: `aws stepfunctions start-execution --state-machine-arn <State_Machine_ARN> --input "{\"Date\": \"2026-06-24\"}"` (sử dụng trình bọc rtk).
- **Xác minh (Verification)**: Bảng điều khiển Step Functions hiển thị trạng thái màu xanh "Running".

### Bước 3 - Gọi endpoint ALB của AI Engine (Step 3 - Invoke AI Engine ALB endpoint)
- **Hành động (Action)**: Giám sát luồng công việc Step Functions thu thập dữ liệu khi nó đạt đến trạng thái chấm điểm AI (AI scoring state).
- **Hành động nội bộ (Internal Action)**: Lambda xử lý dữ liệu truy vấn dữ liệu chi phí được phân vùng thô và thực hiện yêu cầu HTTP POST đến endpoint ALB nội bộ của AI Engine API.
- **Xác minh (Verification)**: Kiểm tra nhật ký thực thi Lambda để tìm phản hồi HTTP 200 và kiểm tra sự lan truyền chính xác của correlation ID.

### Bước 4 - Thực thi tác vụ container AI Engine (Step 4 - Execute AI Engine container task)
- **Hành động (Action)**: Quan sát tác vụ container AI Engine đang chạy trên ECS Fargate.
- **Hành động nội bộ (Internal Action)**: Container xử lý các đặc trưng chi phí, đánh giá điểm độ tin cậy bất thường (ví dụ: 0.89), tạo văn bản giải thích và ghi kết quả vào bảng DynamoDB lưu trữ các bản ghi bất thường.
- **Xác minh (Verification)**: Kiểm tra bảng DynamoDB anomaly để tìm bản ghi mới được chèn với trạng thái `PendingReview`.

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

### Bước 7 - Thực thi containment ở chế độ giả lập (Step 7 - Execute dry-run containment)
- **Hành động (Action)**: Kiểm tra nhật ký kiểm toán containment.
- **Hành động nội bộ (Internal Action)**: Containment engine thực thi các kiểm tra chính sách trên tài nguyên mục tiêu. Vì tài nguyên được đánh dấu dưới các quy tắc sản xuất (production), engine sẽ thực thi ở chế độ `dry-run`.
- **Xác minh (Verification)**: Xác minh rằng instance EC2 AWS mục tiêu vẫn đang chạy, nhưng bảng nhật ký kiểm toán DynamoDB có một bản ghi mới hiển thị hành động được đề xuất `stop_instance` với `execution_mode: dry-run`.

### Bước 8 - Thực thi giả lập hoàn tác (Step 8 - Execute rollback simulation)
- **Hành động (Action)**: Khôi phục trạng thái containment giả lập từ giao diện bảng điều khiển.
- **Hành động nội bộ (Internal Action)**: Quản trị viên nhấp vào nút "Revert" trên bảng điều khiển CDO, thực thi các bước rollback được xác định trong bản ghi kiểm toán (ví dụ: khôi phục trạng thái tag ban đầu).
- **Xác minh (Verification)**: Kiểm tra nhật ký CLI và các bản ghi DynamoDB để xác nhận trạng thái kiểm toán thay đổi thành `RollbackCompleted`.

---

## 2. Danh sách bằng chứng (Evidence checklist)

Danh sách này phác thảo các tệp nhật ký, bảng cơ sở dữ liệu và thông tin liên lạc cụ thể cần thiết để xác minh tính thực thi thành công của pipeline nền tảng CDO trong các buổi kiểm toán.

- **Các tệp nhật ký CUR trong S3 (CUR logs in S3)**: Các tệp thu thập dữ liệu được lưu trữ dưới `s3://cdo-raw-cost-bucket/exports/` xác nhận khả năng tương thích định dạng dữ liệu thô.
- **Các bản ghi DynamoDB (DynamoDB records)**:
  - Bảng anomalies: Bản ghi chứa `anomaly_id`, `confidence_score` và `explanation` từ AI Engine.
  - Bảng audit trail: Bản ghi chứa đầy đủ 14 trường hành động containment, xác minh `correlation_id` khớp với luồng thực thi Step Functions.
- **Các webhook của Slack (Slack webhooks)**: Nhật ký webhook từ kênh ứng dụng Slack mục tiêu, xác nhận việc gửi payload JSON chính xác mà không để lộ cấu trúc chi phí thô.
- **Ảnh chụp màn hình QuickSight / Bảng điều khiển (QuickSight / Dashboard screenshots)**: Các tham chiếu hình ảnh độ phân giải cao hiển thị:
  - Xu hướng chi tiêu hàng ngày với điểm bất thường được đánh dấu phủ lên.
  - Danh sách containment đang hoạt động chi tiết hóa nhãn chế độ `dry-run`.
- **Nhật ký tag CLI (CLI tag logs)**: Nhật ký API CloudTrail xác nhận các cuộc gọi API `ec2:CreateTags` ở chế độ dry-run khớp với ARN instance mục tiêu.

---

## 3. Các điểm thuyết phục của CDO (CDO pitch points)

Các điểm bán hàng chính của kiến trúc data lakehouse tập trung vào hồ dữ liệu serverless cho kiểm soát FinOps:

- **Tiết kiệm chi phí nhờ mô hình Serverless (Serverless cost savings)**: Bằng cách chọn S3, Glue và Athena cho data lakehouse, nền tảng hoạt động với chi phí cực thấp so với các cơ sở dữ liệu luôn chạy truyền thống (RDS/Redshift). Chi phí tính toán chỉ phát sinh trong cửa sổ thực thi truy vấn, mang lại mức tiết kiệm lên tới 90% cho các hoạt động xử lý hàng loạt hàng ngày.
- **Tuân thủ đầy đủ (Complete compliance)**: Nhật ký kiểm toán hai lớp (DynamoDB cho tốc độ giao diện người dùng và S3 với Object Lock cho tính không thể sửa đổi) đảm bảo rằng tất cả các hành động tự động và được đề xuất được bảo tồn trong ít nhất 90 ngày, đáp ứng các quy định kiểm toán tài chính.
- **Vận hành không rủi ro (Risk-free operation)**: Các cấu hình mặc định dry-run nghiêm ngặt trong môi trường sản xuất (production) và chạy thử (staging) giúp ngăn ngừa việc gián đoạn dịch vụ ngoài ý muốn. Tự động hóa được giới hạn một cách an toàn trong môi trường non-production/sandbox nơi các chính sách được thực thi nghiêm ngặt.
- **Cách ly đa người thuê (Multi-tenant isolation)**: Các tiền tố S3 có cấu trúc và phân vùng Glue tách biệt dữ liệu chi phí theo tài khoản và squad. Truy cập chéo tài khoản dựa trên các chính sách IAM assume-role chỉ đọc, ngăn chặn các di chuyển ngang không được phép.

---

## 4. Phản hồi các câu hỏi hóc búa (Curveball responses)

Các lập luận kiến trúc cho các câu hỏi thử thách phổ biến:

- **Làm thế nào để xử lý độ trễ xuất dữ liệu CUR của AWS (lên tới 24 giờ)? (How do you handle AWS CUR data export lag?)**
  - *Phản hồi*: Mặc dù các bản xuất CUR có độ trễ cố định, chu kỳ lập lịch 24 giờ của chúng tôi (ADR-001) được thiết kế để căn chỉnh với chu kỳ này. Để thu hẹp khoảng cách cho các cảnh báo thời gian thực quan trọng, data plane của chúng tôi kết hợp các bản xuất CUR với các cuộc gọi hàng ngày đến AWS Cost Explorer API, nơi cung cấp các dữ liệu tổng hợp chi phí có độ trễ thấp hơn.
- **Làm thế nào để xử lý các cảnh báo giả của AI Engine (mở rộng quy mô bình thường bị phân loại là bất thường)? (How do you handle AI Engine false positives?)**
  - *Phản hồi*: Tư thế containment ưu tiên an toàn của chúng tôi (ADR-005) đảm bảo rằng không có hành động hủy hoại tự động nào được thực hiện trên các tài nguyên sản xuất. Hơn nữa, các squad kỹ thuật nhận được cảnh báo Slack kèm theo nút "Snooze", cho phép họ đánh dấu phân loại đó là mở rộng quy mô bình thường và ngăn chặn các kích hoạt containment tiếp theo cho tài nguyên đó.
- **Điều gì xảy ra nếu một lỗi phần mềm kích hoạt containment tự động trên các tài nguyên sản xuất? (What happens if a bug triggers automated containment on production assets?)**
  - *Phản hồi*: Containment trong môi trường sản xuất được khóa cứng ở chế độ dry-run ở cả cấp chính sách IAM và cấp thời gian chạy (runtime) của Lambda. Ngay cả trong trường hợp hỏng cơ sở dữ liệu hoặc lỗi mã nguồn, các vai trò IAM được gán cho Lambda thực thi containment không sở hữu các quyền cần thiết để xóa, hủy hoặc tắt các tài nguyên sản xuất.
- **Nền tảng xử lý tình trạng throttling API của AWS Cost Explorer như thế nào trong quá trình mở rộng quy mô? (How does the platform handle AWS Cost Explorer API throttling during scaling?)**
  - *Phản hồi*: Lambda thu thập dữ liệu tích hợp cơ chế thử lại với exponential backoff. Ngoài ra, kết quả truy vấn được lưu vào bộ nhớ đệm cục bộ trong S3 trong suốt thời gian chạy để ngăn các yêu cầu API trùng lặp cho cùng một khoảng ngày.
- **Điều gì xảy ra nếu bảng điều khiển bị mất đồng bộ với các tài nguyên AWS thực tế? (What happens if the dashboard becomes out-of-sync with actual AWS resources?)**
  - *Phản hồi*: Các tài nguyên tĩnh của bảng điều khiển được cập nhật ngay lập tức vào cuối mỗi lần chạy pipeline. Một invalidation CloudFront được kích hoạt bằng lập trình để xóa các bộ nhớ đệm ở cạnh. Một nút "Sync Now" cũng được cung cấp trên giao diện để truy vấn trực tiếp các bản ghi DynamoDB.
- **Bảo mật hoàn tác được thực thi như thế nào để ngăn chặn các thay đổi tài nguyên trái phép? (How is rollback security enforced to prevent unauthorized resource changes?)**
  - *Phản hồi*: Việc thực thi hoàn tác yêu cầu các quyền IAM và xác minh MFA tương tự. Mỗi yêu cầu rollback phải được gắn với một ID sự cố hoặc change ticket hợp lệ, và hành động này được ghi nhật ký đầy đủ vào nhật ký kiểm toán WORM trong S3.

---

## 5. Câu hỏi mở (Open questions)

- [ ] **Bảo mật tích hợp Slack Webhook (Slack Webhook Integration Security)**: Chúng ta có nên chuyển đổi từ Slack incoming webhooks tĩnh sang một ứng dụng Slack an toàn sử dụng các mã thông báo OAuth của AWS Secrets Manager để tăng kiểm soát định tuyến không?
- [ ] **Tên miền tùy chỉnh cho Cognito OIDC (Cognito OIDC Custom Domain)**: Nhóm Finance có yêu cầu xác thực người dùng AWS Cognito OIDC tích hợp đăng nhập một lần (SSO) để truy cập bảng điều khiển không?
- [ ] **Tự động hóa hoàn tác sản xuất (Production Rollback Automation)**: Nền tảng nên hỗ trợ tự động hoàn tác bằng một cú nhấp chuột cho các đề xuất tag sản xuất, hay các hoạt động hoàn tác trên sản xuất nên duy trì nghiêm ngặt dưới dạng lệnh CLI thủ công?
- [ ] **Giới hạn truy vấn Athena (Athena Query Limits)**: Giới hạn cứng nào nên được cấu hình cho việc sử dụng dữ liệu truy vấn Athena mỗi ngày để ngăn chặn hóa đơn tăng đột biến do phân tích tự do?
