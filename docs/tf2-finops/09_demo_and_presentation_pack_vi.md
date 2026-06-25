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
- **Thông số kỹ thuật Telemetry (Telemetry Specifications)**: Dữ liệu telemetry là dạng hybrid, kết hợp dữ liệu chi phí (S3 CUR partition pulls và Cost Explorer API queries) với dữ liệu đo lường hiệu suất CloudWatch (`resource_utilization_metrics` như CPU utilization, bộ nhớ, kết nối cơ sở dữ liệu và I/O đĩa). Nếu thiếu dữ liệu đo lường hiệu suất CloudWatch, hệ thống tự động kích hoạt chế độ dự phòng CUR-only, làm giảm một nửa độ tin cậy phát hiện (`confidence *= 0.5`) và giới hạn các biện pháp can thiệp ở chế độ dry-run/cảnh báo thuần túy.
- **Payload**: Một lô các bản ghi EC2 giả lập hiển thị mức tăng chi phí đột ngột gấp 10 lần trên một cụm instance GPU không được quản lý (ví dụ: chi tiêu 500 USD cho EC2 g5.4xlarge).
- **Xác minh (Verification)**: Kiểm tra đường dẫn tệp S3 raw zone: `s3://cdo-raw-cost-bucket/exports/year=2026/month=06/`.

### Bước 2 - Kích hoạt bộ lập lịch pipeline (Step 2 - Trigger pipeline scheduler)
- **Hành động (Action)**: Kích hoạt thủ công quy tắc EventBridge Scheduler hoặc chạy lệnh kích hoạt qua AWS CLI.
- **Lệnh CLI (CLI Command)**: `aws stepfunctions start-execution --state-machine-arn <State_Machine_ARN> --input "{\"Date\": \"2026-06-24\"}"` (sử dụng trình bọc rtk).
- **Xác minh (Verification)**: Bảng điều khiển Step Functions hiển thị trạng thái màu xanh "Running".

### Bước 3 - Gọi AI Engine Request Lambda (Ngữ nghĩa logic POST /v1/detect)
- **Hành động (Action)**: Giám sát luồng công việc Step Functions thu thập dữ liệu khi nó đạt đến trạng thái chấm điểm AI (AI scoring state).
- **Hành động nội bộ (Internal Action)**: Luồng công việc Step Functions trực tiếp gọi hàm AI Engine Request Lambda sử dụng quyền gọi IAM (`lambda:InvokeFunction`).
- **Tham số yêu cầu (truyền trong payload gọi Lambda)**:
  - `X-Tenant-Id`: Xác định bên thuê (ví dụ: `CDO-01`).
  - `X-Idempotency-Key`: Khóa kết hợp format `tenant_id:YYYY-MM-DD` (ví dụ: `CDO-01:2026-06-24`).
  - `X-Correlation-Id`: UUID theo dõi luồng thực thi.
  - `X-Payload-SHA256`: Mã băm SHA256 của payload yêu cầu để kiểm tra tính toàn vẹn.
  - `X-Request-Timestamp`: Nhãn thời gian định dạng ISO 8601.
- **Payload yêu cầu**:
  - Schema URL: `telemetry://finops-watch/v3`.
  - Ingestion Type: `RAW_JSON` cho truy vấn Cost Explorer API (<10MB) hoặc `S3_POINTER` cho dữ liệu CUR trong S3 (<500MB).
  - Control Flags: `is_ad_hoc` (bỏ qua kiểm tra idempotency 24h cho các quét khẩn cấp), `is_estimated` (chi tiêu ước tính từ CE, làm giảm độ tin cậy và bỏ qua tự động containment), `is_forced_dry_run` (nếu độ hoàn thiện dữ liệu telemetry < 0.8, bắt buộc chạy chế độ dry-run).
  - Dữ liệu Telemetry: Chi phí, metadata, và các chỉ số hiệu suất CloudWatch (với cơ chế tự động chuyển sang chế độ CUR-only nếu thiếu dữ liệu hiệu suất).
- **Xác minh (Verification)**: Kiểm tra nhật ký thực thi Lambda để tìm phản hồi gọi thành công chứa:
  - `correlation_id` (UUID theo dõi)
  - `status`: `"processing"`
  - `retry_after_seconds`: `30`

### Bước 4 - Thăm dò trạng thái (Ngữ nghĩa logic GET /v1/status/{correlation_id}) (Step 4 - Poll status)
- **Hành động (Action)**: Giám sát luồng công việc Step Functions tự động thăm dò (polling) bảng thực thi/kết quả DynamoDB trực tiếp theo `correlation_id` sau mỗi 30 giây.
- **Hành động nội bộ (Internal Action)**: SQS lưu đệm các request; hàm Worker Lambda container thực thi chấm điểm mô hình AI, đánh giá điểm độ tin cậy bất thường và tổng hợp chi tiết RCA, ghi nhận kết quả trực tiếp vào DynamoDB và S3.
- **Payload kết quả (lưu trữ trong DynamoDB/S3)**:
  - `correlation_id`: Khớp với UUID thực thi.
  - `status`: `"completed"` hoặc `"failed"`.
- **Xác minh & Biện pháp an toàn (Verification & Fail-safes)**:
  - Nếu phát hiện trùng lặp khóa idempotency, Request Lambda trả về cấu trúc phản hồi xung đột (đại diện cho ngữ nghĩa HTTP `409`).
  - Nếu gửi khóa trùng lặp nhưng payload khác nhau, Request Lambda trả về cấu trúc phản hồi không khớp payload (đại diện cho ngữ nghĩa HTTP `400` với mã lỗi `ERR_IDEMPOTENCY_MISMATCH`).
  - Nếu Bedrock bị quá thời hạn phản hồi (giới hạn cứng Bedrock API 45 giây, trả về mã lỗi `ERR_LLM_TIMEOUT` trong kết quả) hoặc dịch vụ bị dừng (`ERR_SERVICE_DOWN`), pipeline lập tức kích hoạt rules engine tĩnh và cảnh báo đội ngũ SRE.
  - Kiểm tra bảng bản ghi bất thường DynamoDB để xác minh bản ghi mới được ghi nhận với chuỗi liên kết kiểm toán mã hóa (cryptographic audit trail chain) tính toán theo công thức `sha256(current_payload + previous_hash)`.

### Bước 5 - Nhận Kế hoạch Can thiệp (Ngữ nghĩa logic POST /v1/decide) (Step 5 - Get Intervention Plan)
- **Hành động (Action)**: Khi trạng thái hoàn thành, Step Functions gọi hàm AI Engine worker Lambda (đại diện cho ngữ nghĩa `/v1/decide`) để nhận báo cáo phân tích nguyên nhân gốc rễ (RCA) và kế hoạch hành động containment.
- **Tham số yêu cầu (Request Parameters)**: Các headers `X-Correlation-Id` và `X-Tenant-Id`.
- **Xác minh (Verification)**: Xác minh rằng AI Engine trả về kế hoạch chứa mã lệnh AWS CLI chính xác (ví dụ: `aws ec2 create-tags` ở chế độ dry-run) và payload lệnh hoàn tác rollback tương ứng.

### Bước 6 - Xác thực và truy cập bảng điều khiển CDO (Cognito Hosted UI) (Step 6 - Authenticate and access CDO dashboard)
- **Hành động (Action)**: Mở URL CloudFront của bảng điều khiển trong trình duyệt. Xác minh bạn tự động được chuyển hướng đến màn hình đăng nhập Cognito Hosted UI. Đăng nhập bằng tài khoản người dùng Finance (liên kết với nhóm `finops-finance-readonly`).
- **Hành động nội bộ (Internal Action)**: CloudFront chuyển tiếp yêu cầu sau khi lớp xác thực Lambda@Edge chặn yêu cầu, xác thực token Cognito JWT và gửi đến bucket S3 riêng tư. Giao diện dashboard phân tích thông tin claim nhóm trong mã JWT.
- **Xác minh (Verification)**: Xác nhận biểu đồ xu hướng chi tiêu hàng ngày và các điểm bất thường được hiển thị thành công, nhưng các nút kích hoạt thực thi Kế hoạch Hành động và các nút hoàn tác Rollback hoàn toàn bị vô hiệu hóa hoặc ẩn đi. Nếu khóa ngân sách lỗi (error budget lock) đang hoạt động (tỷ lệ rollback thủ công vượt quá 1% trong 30 ngày), xác minh rằng một banner đỏ cảnh báo nổi bật hiển thị tenant đang ở chế độ `LOCKED_MODE`.

### Bước 7 - Định tuyến cảnh báo (Step 7 - Route alerts)
- **Hành động (Action)**: Kiểm tra các kênh thông báo.
- **Hành động nội bộ (Internal Action)**: Alert Routing Lambda kiểm tra mức độ nghiêm trọng của bất thường và các tag sở hữu của squad.
- **Xác minh (Verification)**: 
  - Slack: Xác minh rằng một tin nhắn thông báo đã đến kênh `#squad-prediction-models` chứa ARN tài nguyên, chi phí chênh lệch, correlation ID và liên kết bảng điều khiển.
  - SES/SNS: Xác minh rằng danh sách gửi thư của Finance đã nhận được email tóm tắt về đột biến chi phí và đề xuất kế hoạch hành động.

### Bước 8 - Thực thi containment ở chế độ giả lập (được xác thực bởi Cognito) (Step 8 - Execute dry-run containment)
- **Hành động (Action)**: Đăng xuất khỏi phiên làm việc Finance và đăng nhập lại bằng tài khoản điều hành viên Kỹ thuật (thuộc nhóm `finops-engineering-operator`). Tìm bất thường đang hoạt động trên dashboard và nhấp vào nút "Execute Plan" (Thực thi Kế hoạch).
- **Hành động nội bộ (Internal Action)**: Giao diện dashboard kích hoạt Lambda xử lý containment. Lớp Lambda@Edge xác thực cookie JWT đang hoạt động, kiểm tra tư cách thành viên nhóm, và cho phép thực hiện thao tác.
- **Xác minh (Verification)**: Xác minh instance EC2 AWS mục tiêu vẫn đang chạy, nhưng bảng nhật ký kiểm toán DynamoDB có một bản ghi mới hiển thị hành động đề xuất `stop_instance` với `execution_mode: dry-run` và một chuỗi liên kết kiểm toán mã hóa.

### Bước 9 - Xác minh tính hiệu quả của containment (Ngữ nghĩa logic POST /v1/verify) (Step 9 - Verify containment effectiveness)
- **Hành động (Action)**: Nền tảng CDO (hoặc Step Functions workflow) gọi trực tiếp hàm Lambda tương ứng `/v1/verify` truyền vào `correlation_id` và dữ liệu telemetry sau can thiệp.
- **Hành động nội bộ (Internal Action)**: AI Engine so sánh các chỉ số hiệu suất sau can thiệp với dữ liệu baseline lịch sử để đánh giá kết quả containment.
- **Xác minh (Verification)**: Xác minh API trả về trạng thái kết quả `DONE`, `RETRY`, hoặc `ROLLBACK` và ghi nhận kết quả xác thực.

### Bước 10 - Thực thi hoàn tác thủ công/tự động (Ngữ nghĩa logic POST /v1/audit/{audit_id}/rollback) (Step 10 - Execute manual/auto rollback)
- **Hành động (Action)**: Trong khi đăng nhập dưới quyền điều hành viên Kỹ thuật, nhấp vào nút "Revert/Rollback" trên dashboard, hoặc khi xác thực kết quả can thiệp trả về `ROLLBACK` kích hoạt tự động hoàn tác.
- **Hành động nội bộ (Internal Action)**: Dashboard/workflow kích hoạt Lambda xử lý rollback (đại diện cho ngữ nghĩa `/v1/audit/{audit_id}/rollback`) cùng thông tin phiên đăng nhập Cognito. Backend kiểm tra thông tin claim nhóm Cognito, xác minh ngữ cảnh bên thuê (tenant context), và kích hoạt hoàn tác tag.
- **Xác minh (Verification)**: Kiểm tra nhật ký CLI và bản ghi DynamoDB để xác nhận trạng thái kiểm toán thay đổi thành `RollbackCompleted` với ID người dùng Cognito của điều hành viên được ghi lại trong trường `actor`. Xác nhận nỗ lực của người dùng Finance sẽ trả về lỗi phân quyền (đại diện cho lỗi HTTP `403 Forbidden` dưới dạng dữ liệu logic) và tạo ra bản ghi kiểm toán `unauthorized_action_blocked`. Nếu tỷ lệ rollback thủ công vượt quá 1% trong chu kỳ 30 ngày, xác minh tenant bị khóa vào trạng thái `LOCKED_MODE` (bắt buộc mọi quyết định sau đó chạy dry-run).

---

## 2. Danh sách bằng chứng (Evidence checklist)

Danh sách này phác thảo các tệp nhật ký, bảng cơ sở dữ liệu và thông tin liên lạc cụ thể cần thiết để xác minh tính thực thi thành công của pipeline nền tảng CDO trong các buổi kiểm toán.

- **Các tệp nhật ký CUR trong S3 (CUR logs in S3)**: Các tệp thu thập dữ liệu được lưu trữ dưới `s3://cdo-raw-cost-bucket/exports/` xác nhận khả năng tương thích định dạng dữ liệu thô.
- **Xác minh VPC Flow Logs & IAM Telemetry**: Nhật ký cho thấy log thực thi gọi Lambda trực tiếp và lưu lượng qua VPC Endpoint không có lưu lượng thoát ra internet.
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
- **Tối ưu hóa hosting AI dùng chung (Shared AI hosting optimization)**: Việc triển khai AI Engine dưới dạng các hàm AWS Lambda container gọi trực tiếp qua hàng đợi SQS giúp tối ưu hóa dung lượng tính toán giữa nhiều nền tảng CDO (loại bỏ chi phí nhàn rỗi) trong khi vẫn giữ cách ly khối lượng công việc thông qua header `X-Tenant-Id` và phân quyền gọi hàm của IAM.
- **Tuân thủ đầy đủ (Complete compliance)**: Nhật ký kiểm toán hai lớp (DynamoDB cho tốc độ giao diện người dùng và S3 với Object Lock cho tính không thể sửa đổi) đảm bảo rằng tất cả các hành động tự động và được đề xuất được bảo tồn trong ít nhất 90 ngày, đáp ứng các quy định kiểm toán tài chính. Mỗi mục nhật ký kiểm toán được liên kết mã hóa bằng `sha256(current_payload + previous_hash)` để chống giả mạo.
- **Vận hành không rủi ro (Risk-free operation)**: Các cấu hình mặc định dry-run nghiêm ngặt trong môi trường sản xuất (production) và chạy thử (staging) giúp ngăn ngừa việc gián đoạn dịch vụ ngoài ý muốn. Tự động hóa được giới hạn một cách an sau trong môi trường non-production/sandbox nơi các chính sách được thực thi nghiêm ngặt.
- **Cách ly đa người thuê (Multi-tenant isolation)**: Các tiền tố S3 có cấu trúc và phân vùng Glue tách biệt dữ liệu chi phí theo tài khoản và squad. Truy cập chéo tài khoản dựa trên các chính sách IAM assume-role chỉ đọc, ngăn chặn các di chuyển ngang không được phép.

---

## 4. Phản hồi các câu hỏi hóc búa (Curveball responses)

Các lập luận kiến trúc cho các câu hỏi thử thách phổ biến:

- **Làm thế nào để xử lý độ trễ xuất dữ liệu CUR của AWS (lên tới 24 giờ)? (How do you handle AWS CUR data export lag?)**
  - *Phản hồi*: Mặc dù các bản xuất CUR có độ trễ cố định, chu kỳ lập lịch 24 giờ của chúng tôi (ADR-001) được thiết kế để căn chỉnh với chu kỳ này. Để thu hẹp khoảng cách cho các cảnh báo thời gian thực quan trọng, data plane của chúng tôi kết hợp các bản xuất CUR với các cuộc gọi hàng ngày đến AWS Cost Explorer API, nơi cung cấp các dữ liệu tổng hợp chi phí có độ trễ thấp hơn.
- **Làm thế nào để xử lý các cảnh báo giả của AI Engine (mở rộng quy mô bình thường bị phân loại là bất thường)? (How do you handle AI Engine false positives?)**
  - *Phản hồi*: Tư thế containment ưu tiên an toàn của chúng tôi (ADR-005) đảm bảo rằng không có hành động hủy hoại tự động nào được thực hiện trên các tài nguyên sản xuất. Hơn nữa, các squad kỹ thuật nhận được cảnh báo Slack và dashboard hiển thị chi tiết kế hoạch can thiệp được đề xuất. Điều hành viên Kỹ thuật có thể xem xét thủ công và bấm nút "Execute Plan" (Thực thi Kế hoạch), hoặc hoàn tác hành động nếu phát hiện cảnh báo giả. Ngoài ra, dữ liệu telemetry phát hiện là dạng hybrid (CUR + Cost Explorer + CloudWatch utilization metrics), giúp nâng cao độ chính xác phân loại. Nếu thiếu dữ liệu CloudWatch, hệ thống tự động chuyển sang chế độ CUR-only, làm giảm một nửa độ tin cậy phát hiện (`confidence *= 0.5`) và khóa containment ở chế độ dry-run hoặc cảnh báo, ngăn chặn các hành động sai lệch.
- **Điều gì xảy ra nếu một lỗi phần mềm kích hoạt containment tự động trên các tài nguyên sản xuất? (What happens if a bug triggers automated containment on production assets?)**
  - *Phản hồi*: Containment trong môi trường sản xuất được khóa cứng ở chế độ dry-run ở cả cấp chính sách IAM và cấp thời gian chạy (runtime) của Lambda (Giá trị An toàn: `Never`). Ngay cả trong trường hợp hỏng cơ sở dữ liệu hoặc lỗi mã nguồn, các vai trò IAM được gán cho Lambda thực thi containment không sở hữu các quyền cần thiết để xóa, hủy hoặc tắt các tài nguyên sản xuất.
- **Nền tảng xử lý tình trạng throttling API của AWS Cost Explorer như thế nào trong quá trình mở rộng quy mô? (How does the platform handle AWS Cost Explorer API throttling during scaling?)**
  - *Phản hồi*: Lambda thu thập dữ liệu tích hợp cơ chế thử lại với exponential backoff. Ngoài ra, kết quả truy vấn được lưu vào bộ nhớ đệm cục bộ trong S3 trong suốt thời gian chạy để ngăn các yêu cầu API trùng lặp cho cùng một khoảng ngày.
- **Điều gì xảy ra nếu bảng điều khiển bị mất đồng bộ với các tài nguyên AWS thực tế? (What happens if the dashboard becomes out-of-sync with actual AWS resources?)**
  - *Phản hồi*: Các tài nguyên tĩnh của bảng điều khiển được cập nhật ngay lập tức vào cuối mỗi lần chạy pipeline. Một invalidation CloudFront được kích hoạt bằng lập trình để xóa các bộ nhớ đệm ở cạnh. Một nút "Sync Now" cũng được cung cấp trên giao diện để truy vấn trực tiếp các bản ghi DynamoDB.
- **Bảo mật hoàn tác được thực thi như thế nào để ngăn chặn các thay đổi tài nguyên trái phép? (How is rollback security enforced to prevent unauthorized resource changes?)**
  - *Phản hồi*: Việc thực thi hoàn tác gọi Lambda adapter hoàn tác, kích hoạt endpoint `/v1/audit/{audit_id}/rollback`. Nó yêu cầu các quyền IAM và xác minh MFA tương tự. Mỗi yêu cầu rollback được xác thực phân quyền qua Cognito, xác minh ngữ cảnh tenant và ghi nhật ký kiểm toán vào kho lưu trữ WORM trong S3. Nếu tỷ lệ rollback thủ công vượt quá 1% trong chu kỳ 30 ngày, hệ thống tự động kích hoạt khóa ngân sách lỗi (`LOCKED_MODE`), bắt buộc mọi hành động can thiệp tiếp theo chạy dry-run/cảnh báo cho đến khi sự cố được khắc phục.
- **Ai sở hữu triển khai và vòng đời vận hành Lambda container của AI Engine dùng chung? (Who owns the Lambda container deployment and operational lifecycle of the shared AI Engine?)**
  - *Phản hồi*: CDO sở hữu việc triển khai hạ tầng host (VPC, subnets, Lambda functions, giới hạn concurrency, role execution, queues, và DynamoDB state stores) để đảm bảo tính sẵn sàng, bảo mật của hệ thống và kiểm soát thực thi IAM. AIOps sở hữu logic mô hình AI, logic RCA/khuyến nghị, thực thi rules engine dự phòng cục bộ, tuân thủ hợp đồng API nội bộ, và build container image.
- **Điều gì xảy ra nếu AI Engine gặp lỗi, quá thời gian phản hồi, hoặc nhận được các yêu cầu trùng lặp? (What happens if the AI Engine fails, times out, or receives duplicate requests?)**
  - *Phản hồi*: Nếu AI Engine phát hiện các khóa idempotency trùng lặp, nó trả về cấu trúc phản hồi xung đột (đại diện cho ngữ nghĩa HTTP `409`), hoặc cấu trúc không khớp (đại diện cho ngữ nghĩa HTTP `400` với mã lỗi `ERR_IDEMPOTENCY_MISMATCH`) nếu các payload khác nhau. Nếu Bedrock bị hết thời gian chờ (giới hạn cứng 45s của Bedrock API, trả về mã lỗi `ERR_LLM_TIMEOUT`) hoặc dịch vụ bị lỗi (`ERR_SERVICE_DOWN`), pipeline CDO sẽ lập tức chuyển sang thực thi rules engine tĩnh và kích hoạt cảnh báo SRE, đảm bảo một trạng thái containment an toàn tuyệt đối.

---

## 5. Câu hỏi mở (Open questions)

- [ ] **Bảo mật tích hợp Slack Webhook (Slack Webhook Integration Security)**: Chúng ta có nên chuyển đổi từ Slack incoming webhooks tĩnh sang một ứng dụng Slack an sau sử dụng các mã thông báo OAuth của AWS Secrets Manager để tăng kiểm soát định tuyến không?
- [ ] **Đăng nhập một lần với Cognito OIDC (Cognito OIDC Single Sign-On - SSO)**: Chúng ta có nên tích hợp Cognito User Pool với nhà cung cấp danh tính Okta/O365 của doanh nghiệp để đăng nhập một lần (SSO) thay vì duy trì danh bạ người dùng độc lập không?
- [ ] **Giới hạn truy vấn Athena (Athena Query Limits)**: Giới hạn cứng nào nên được cấu hình cho việc sử dụng dữ liệu truy vấn Athena mỗi ngày để ngăn chặn hóa đơn tăng đột biến do phân tích tự do?
- [ ] **Ngân sách Token cho mô hình Bedrock (Bedrock Model Token Budget)**: Giới hạn token nào nên được thiết lập cho mỗi tenant trong cấu hình Secrets Manager để tránh chi phí Bedrock vượt trội khi gặp số lượng lớn bất thường chi phí đột biến? (`Cần bằng chứng: đo kiểm chi phí Bedrock/token theo baseline thực tế`)
