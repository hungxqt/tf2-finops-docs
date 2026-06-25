# Báo cáo Kiểm thử và Đánh giá (Test & Eval Report) - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Refined (W12 T4 Pack #2)
-->

> [!IMPORTANT]
> **Ranh giới Bảo mật**: Mọi quy trình kiểm thử và xác thực phải xác nhận rằng nền tảng tuân thủ nghiêm ngặt ranh giới cứng: **NEVER terminate prod, delete data, hoặc modify IAM**.


## 1. Phạm vi kiểm thử (Test coverage)

Việc xác minh nền tảng FinOps Watch CDO được thực hiện trên nhiều cấp độ kiểm thử khác nhau nhằm đảm bảo tính toàn vẹn của hoạt động vận hành, sự tuân thủ nghiêm ngặt đối với hợp đồng AI Engine do nhóm AIOps cung cấp, và các hành vi containment an toàn.

| Loại kiểm thử (Test Type) | Công cụ (Tool) | Phạm vi / Mô tả (Scope / Description) |
|---|---|---|
| Unit | pytest | Xác thực các Lambda handlers riêng lẻ viết bằng Python, các hàm tiện ích, các hàm hỗ trợ tính toán chi phí và các adapter dữ liệu. |
| Integration | AWS SDK mock (boto3 mock / moto), pytest | Xác minh các hoạt động ghi S3, ghi có thẩm quyền trên S3 (S3 authoritative writes), xử lý hàng đợi SQS cho cảnh báo, và gửi thông báo SNS/SES. |
| E2E (End-to-End) | Custom test harnesses, CLI scripts | Thực thi toàn bộ luồng dữ liệu từ việc chèn bất thường giả lập trong CUR, lập lịch, gọi trực tiếp AI Engine, cập nhật S3, cho đến định tuyến cảnh báo và dry-run đối với containment. |
| Scheduled-Run Idempotency | Custom test scripts | Xác nhận rằng việc xử lý cùng một chu kỳ thanh toán CUR hai lần không tạo ra các đối tượng trùng lặp trên S3 hoặc kích hoạt các hành động cảnh báo/containment trùng lặp. |
| Chaos / Failure | AWS Fault Injection Service (FIS) | Giả lập các phân vùng mạng, giới hạn tần suất gọi API (throttling) của Cost Explorer API, độ trễ của S3/DB và tình trạng AI Engine không khả dụng để xác minh các đường dẫn fail-closed và phục hồi mềm dẻo. |

---

## 2. Bằng chứng SLO (SLO evidence)

Hiệu suất vận hành của nền tảng được đánh giá dựa trên các Mục tiêu Mức độ Dịch vụ (SLOs) được thiết lập cho độ tin cậy, độ tươi mới của dữ liệu và tốc độ truyền tải thông tin.

| SLO | Mục tiêu (Target) | Đã đo lường (Measured) | Chu kỳ đánh giá (Window) | Đạt/Không đạt (Pass/Fail) |
|---|---|---|---|---|
| Scheduled Run Success Rate | >=99.9% số lần chạy hàng ngày được lập lịch | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý | 30 ngày (30 Days) | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý |
| Data Freshness | <=24 giờ từ khi CUR khả dụng đến Athena | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý | Chu kỳ hàng ngày (Daily Cycle) | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý |
| Dashboard Refresh Latency | <=5 phút từ khi pipeline hoàn thành đến khi cập nhật tài nguyên tĩnh | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý | Chu kỳ hàng ngày (Daily Cycle) | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý |
| Alert Delivery Latency | <=30 phút từ khi phát hiện bất thường đến khi gửi tới Slack/SNS | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý | Theo từng cảnh báo (Per-Alert) | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý |

### 2.1 Các SLO tích hợp theo hợp đồng (Logical AI Engine Contract)

Việc tuân thủ các giới hạn bắt buộc theo hợp đồng từ `ai-api-contract.md` §6 được đo lường theo chương trình cho đường dẫn thực thi định tuyến qua Private ALB:

| Chỉ số SLO hợp đồng | Mục tiêu | Điểm đo lường | Kết quả xác minh |
|---|---|---|---|
| Độ trễ yêu cầu (P99) | < 300 ms | Thời gian phản hồi của ALB (xác thực đầu vào & chạy phát hiện đồng bộ) | Cần bằng chứng: số liệu đo lường |
| Độ trễ truy vấn kết quả (P99) | < 10 ms | Độ trễ GetObject trên S3 cho `correlation_id` / `anomaly_id` | Cần bằng chứng: số liệu đo lường của S3 |
| SLA suy luận LLM | < 30 giây | Thời gian chạy logic suy luận nội bộ của AI Engine Lambda | Cần bằng chứng: số liệu đo lường của AI Engine Lambda |
| Tính khả dụng hệ thống | >=99.5% | Tỷ lệ gọi API HTTPS ALB thành công (không tính lỗi do client bị chặn tần suất) | Cần bằng chứng: số liệu CloudWatch metrics |
| Tỷ lệ lỗi Ingestion | < 0.5% | Số lần chạy lỗi (lượt chạy lỗi / tổng số yêu cầu xử lý CUR) | Cần bằng chứng: số liệu đo lường |

### 2.2 Phân tích vi phạm SLO (SLO breach analysis)

Trong trường hợp xảy ra vi phạm SLO, các quy trình leo thang và khắc phục sau sẽ được kích hoạt:
- **Cost Explorer Throttling**: Nếu vượt quá giới hạn tần suất gọi API của Cost Explorer API, Lambda thu thập dữ liệu sẽ bắt lấy ngoại lệ và thử lại bằng chiến lược exponential backoff. Nếu lượt chạy vượt quá cửa sổ SLA 24 giờ, nhóm vận hành sẽ được cảnh báo qua PagerDuty.
- **AI Engine Lambda Startup Timeouts / Cold Starts**: Nếu các hàm Lambda container không khởi động được hoặc gặp độ trễ lớn (cold start) trong các sự kiện mở rộng quy mô cao điểm, nền tảng sẽ kích hoạt cảnh báo để thực hiện tối ưu hóa Provisioned Concurrency hoặc ủy thác xử lý thử lại để duy trì SLO về độ trễ.
- **S3 / CloudFront Invalidation Delays**: Nếu các bản cập nhật JSON của dashboard không phân phối được do hành vi bộ nhớ đệm của CloudFront, API invalidation sẽ tự động được thử lại bởi pipeline triển khai trang web tĩnh.

---

## 3. Các kiểm thử nền tảng CDO (CDO platform tests)

### 3.1 Thu thập dữ liệu (Data ingestion)

Xác minh Thu thập dữ liệu (Data Ingestion) tập trung vào việc lấy và phân tích cú pháp dữ liệu chi phí từ AWS Data Exports (CUR 2.0) và AWS Cost Explorer API:
- **Raw Ingestion**: Lambda thu thập dữ liệu thô lấy các tệp parquet/CSV từ S3 bucket thanh toán và xác minh rằng các định nghĩa schema khớp với cấu trúc đã xác định.
- **Cost Explorer Queries**: Xác minh rằng các phản hồi giả lập từ Cost Explorer API khớp với các kỳ vọng lịch sử và được ánh xạ tới các cửa sổ chi phí được chuẩn hóa.
- **Glue Catalog & Athena Partition Projection (ADR-014)**: Các quy trình kiểm thử bao gồm cả hai giai đoạn. Đầu tiên, các kiểm thử xác minh tính hợp lệ của schema bằng cách sử dụng Athena SQL DDL trong quá trình thiết kế schema ban đầu đối với các tệp CUR giả lập. Thứ hai, các kiểm thử xác minh rằng các định nghĩa bảng trong Glue Data Catalog được áp dụng chính xác thông qua Terraform IaC, và tính năng client-side Athena Partition Projection tự động phân tích các phân vùng raw trên S3 tại thời điểm thực thi truy vấn mà không phụ thuộc vào crawler ở runtime, cho phép các truy vấn tổng hợp các chỉ số chi phí theo dịch vụ, khu vực, tài khoản và các tag tài nguyên mà không gặp lỗi cú pháp. Dưới thiết kế telemetry lai (hybrid telemetry), các dữ liệu CUR và Cost Explorer được kết hợp với các chỉ số hiệu năng từ CloudWatch (`resource_utilization_metrics` như CPU, memory, database connections, GPU metrics). Nếu các chỉ số CloudWatch không khả dụng, hệ thống tự động chuyển sang chế độ CUR-only, thiết lập `data_confidence = LOW` và bắt buộc thực hiện các hành động containment ở chế độ dry-run/alert-only. Các tệp log và metrics của CloudWatch cũng được sử dụng cho việc giám sát sức khỏe vận hành của CDO platform và dashboard.

### 3.2 Tính không thay đổi của lượt chạy theo lịch trình (Scheduled run idempotency)

Pipeline chạy theo một chu kỳ được lập lịch (ADR-001) được kích hoạt bởi EventBridge Scheduler. Để xác minh tính không thay đổi (idempotency):
- **Duplicate Execution Test**: Cùng một phân vùng cửa sổ ngày (ví dụ: 2026-06-22) được gửi hai lần đến luồng công việc thu thập dữ liệu.
- **State Check**: Thành phần compute thu thập dữ liệu thử ghi điều kiện (conditional write) vào bảng DynamoDB `finops-idempotency-{env}` sử dụng composite key.
- **Execution Bypass**: Lượt ghi thứ hai thất bại với lỗi `ConditionalCheckFailedException` (khóa đã tồn tại), giúp lượt chạy thứ hai được bỏ qua một cách thành công và không có đối tượng S3 hay tin nhắn cảnh báo trùng lặp nào được tạo ra.

### 3.3 Làm mới bảng điều khiển (Dashboard refresh)

- **Static Asset Generation**: Một tác vụ Lambda chuyên dụng được thực thi sau khi luồng công việc thu thập dữ liệu kết thúc để tổng hợp và ghi các tệp JSON chứa tóm tắt chi tiêu vào S3 bucket của bảng điều khiển công khai.
- **Frontend Verification**: Kịch bản kiểm thử giả lập một trình duyệt máy khách lấy các cấu trúc JSON đã cập nhật và xác nhận rằng các biểu đồ cập nhật chính xác để phản ánh các điểm chi phí mới.

---

## 4. Các kiểm thử tích hợp AI (AI integration tests)

### 4.1 Hợp đồng AI (AI contract)

Giao diện dựa trên hợp đồng giữa nền tảng CDO và AI Engine (do AIOps sở hữu) được xác minh về tính tuân thủ schema nghiêm ngặt:
- **Xác thực định dạng yêu cầu (Request Format Verification)**: Trình kiểm thử gửi các yêu cầu tuân thủ schema phiên bản `telemetry://finops-watch/v3` chứa các header `X-Tenant-Id`, `X-Idempotency-Key` (composite key: `tenant_id:YYYY-MM-DD:batch_type`), `X-Correlation-Id`, `X-Payload-SHA256`, and `X-Request-Timestamp` tới endpoint ALB nội bộ riêng tư sử dụng HTTPS và xác thực AWS SigV4. Kiểm thử xác minh rằng payload yêu cầu tuân thủ schema dữ liệu đo lường hiệu năng lai (chứa CUR, Cost Explorer và CloudWatch `resource_utilization_metrics`). Nếu các chỉ số CloudWatch bị giả lập là thiếu, kiểm thử xác minh rằng Lambda xử lý việc fallback bằng cách thiết lập `data_confidence = LOW` và bắt buộc chạy ở chế độ dry-run/alert-only.
- **Xác thực định dạng phản hồi (Response Format Verification)**: Kiểm thử xác minh rằng ALB của AI Engine trả về payload đồng bộ chứa các tham số bắt buộc: `success`, `correlation_id`, `anomalies_detected`, và `anomalies_list` (chứa `anomaly_id`, `anomaly_type`, `severity`, `confidence_score`, `resource_id`, `environment`, `responsible_team`, `unblended_cost_24h_usd`, `cost_ratio_to_7d_avg`, `ai_model_used`, `alert_routing`).
- **Xác thực thu nhận với dữ liệu CUR hoàn chỉnh (Ingest Validation with Finalized CUR-only Data)**: Xác minh rằng khi lượt chạy thu thập dữ liệu xử lý dữ liệu CUR đã hoàn chỉnh đúng hạn, payload yêu cầu sẽ khẳng định `telemetry_delay_event = false` và phản hồi trả về chứa `data_confidence = HIGH`.
- **Xác thực cơ chế dự phòng khi CUR bị trễ (Fallback Validation with CUR Delayed)**: Xác minh rằng nếu việc cung cấp dữ liệu CUR bị trễ, yêu cầu sẽ gắn cờ `telemetry_delay_event = true` (báo hiệu rằng cơ chế truy vấn dự phòng Cost Explorer hàng ngày đang hoạt động) và phản hồi sẽ trả về `data_confidence = LOW`.
- **Xác thực schema S3 Bucket URI (S3 Bucket URI Schema Validation)**: Xác minh rằng tham số `s3_bucket_uri` được kiểm tra tính hợp lệ dựa trên mẫu biểu thức chính quy (regex) `s3://company-cdo-[0-9]{12}-telemetry/.*$` (khớp với tiêu chuẩn đặt tên theo tài khoản), trả về lỗi xác thực schema cho các URI không đúng định dạng.
- **Kiểm tra dữ liệu đo lường CPU thô (Raw CPU Telemetry Check)**: Xác nhận rằng nền tảng CDO gửi mảng dữ liệu CPU thô `cpu_utilization_hourly` nguyên bản mà không tính toán trước các chỉ số SRE như `idle_hours_continuous` trên backend của CDO.

### 4.2 Hết thời gian chờ AI Engine (AI Engine timeout)

- **Timeout Simulation**: Một tác vụ container giả lập được cấu hình để trì hoãn thực thi thêm 30 giây (giả lập việc LLM bị chậm).
- **Execution**: Bộ điều phối Step Functions hoặc compute nền tảng của CDO gọi endpoint ALB riêng tư một cách đồng bộ.
- **Verification**: Nếu yêu cầu đến ALB không trả về kết quả trong giới hạn thời gian chờ của bước thực thi Step Functions, nền tảng sẽ ghi lại cảnh báo hết thời gian chờ và gửi cảnh báo tới quản trị viên.

### 4.3 Cơ chế dự phòng khi AI không khả dụng (Unavailable-AI fallback)

Nếu AI Engine hoàn toàn không thể truy cập được (ví dụ: lỗi định tuyến ALB hoặc cạn kiệt concurrency (giới hạn thực thi đồng thời) của hàm Lambda):
- **Fail Closed Behavior**: Nền tảng CDO ngay lập tức hủy bỏ mọi kích hoạt hành động containment theo lịch trình. Không áp dụng chính sách tự động nào.
- **Operator Alert**: Một ticket sự cố nghiêm trọng và cảnh báo PagerDuty được định tuyến đến các nhóm kỹ thuật và tài chính CDO trung tâm.
- **Audit Logging**: Một bản ghi lỗi được ghi vào S3 bucket kiểm toán, chi tiết hóa tình trạng không khả dụng của AI Engine.

### 4.4 Tải container image của Lambda và cold-start (Lambda container image pull & cold-start)

- **Xác thực việc kéo Image**: Kịch bản xác minh kiểm tra cấu hình Lambda để đảm bảo ghim mã băm container image (`image@sha256:...`) và quyền kéo image từ ECR.
- **Hiệu năng Cold-Start**: Đo lường thời gian phản hồi trong quá trình khởi tạo container để đảm bảo nằm trong cửa sổ thời gian thực thi chấp nhận được.
- **Kiểm thử Provisioned Concurrency (Tùy chọn)**: Nếu được kích hoạt, xác minh các môi trường thực thi Lambda được làm ấm sẵn được phân bổ và định tuyến yêu cầu thành công mà không gặp độ trễ cold-start.

### 4.5 Thử lại và redrive hàng đợi SQS/DLQ (SQS/DLQ retry and redrive)

- **Giả lập gián đoạn thực thi (Interruption Mocking)**: Giả lập lỗi hoặc timeout trong quá trình thực thi hàm Lambda định tuyến cảnh báo (alert routing).
- **Độ tin cậy của SQS (SQS Durability)**: Xác minh SQS giữ tin nhắn, tăng bộ đếm số lần nhận (receive count), và kích hoạt lại hàm Lambda định tuyến cảnh báo sau khi visibility timeout hết hạn.
- **Redrive sang DLQ (DLQ Redrive)**: Giả lập việc vượt quá số lần thử lại tối đa và xác minh tin nhắn được đưa an toàn sang Dead Letter Queue (DLQ) để phân tích lỗi, đồng thời ghi bản ghi kiểm toán failure.

### 4.6 Dung lượng đệm hàng SQS và kiểm soát concurrency (SQS message buffering capacity and concurrency controls)

- **Dung lượng đệm hàng SQS (SQS Queue Buffering)**: Xác minh rằng dưới tải đỉnh, Lambda định tuyến cảnh báo (Alert Routing Lambda) đẩy thành công các yêu cầu định tuyến cảnh báo vào hàng SQS mà không bị mất tin nhắn.
- **Kiểm soát Concurrency (Concurrency Rate Limits)**: Xác thực rằng concurrency thực thi của Lambda định tuyến cảnh báo tự động mở rộng theo độ sâu hàng đợi SQS, tuân thủ giới hạn Reserved Concurrency để tránh gây quá tải hạ tầng phía sau.

### 4.7 Kiểm soát concurrency (Concurrency controls)

- **Giả lập tải đồng thời cao (Concurrency Load Simulation)**: Giả lập sự bùng phát lượng cuộc gọi đồng thời trực tiếp tới Lambda của AI Engine.
- **Rào chắn Reserved Concurrency (Reserved Concurrency Guardrail)**: Xác minh hàm Lambda của AI Engine tuân thủ giới hạn Reserved Concurrency đã thiết lập để không gây nghẽn cho các dịch vụ quan trọng khác, trả về lỗi gọi hàm bị throttling phù hợp.
- **Kiểm thử Provisioned Concurrency (Tùy chọn)**: Nếu được kích hoạt, xác minh các môi trường thực thi Lambda được làm ấm sẵn được phân bổ và định tuyến yêu cầu thành công mà không gặp độ trễ cold-start.

### 4.8 Kiểm thử Truy xuất Kết quả & Phân trang (Result Retrieval & Pagination Tests)

- **Xác thực Phản hồi Truy xuất (Retrieval Response Verification)**: Khung kiểm thử truy vấn kho lưu trữ có thẩm quyền S3 (S3 Authoritative store) cho `correlation_id` tương ứng. Nó xác thực cấu trúc của các đối tượng `anomalies_list` được trả về.
- **Xác thực Phân trang (Pagination Validation)**: Dưới tải kiểm thử tạo ra nhiều bất thường, khung kiểm thử truy vấn kết quả với giới hạn kích thước bản ghi để xác minh `next_token` được tạo. Sau đó, nó truy vấn các trang tiếp theo bằng token này, xác nhận thứ tự index kết quả chính xác.

### 4.9 Kiểm thử Hành động Gia hạn & Hoàn tác (Extend & Rollback Semantics Tests)

- **Kiểm thử Kế hoạch Hành động Decide (Decide Action Plan Test)**: Mô phỏng việc bộ điều phối gọi Lambda của AI Engine (đại diện cho ngữ nghĩa `POST /v1/decide`) để lấy kế hoạch can thiệp. Kiểm thử xác minh kế hoạch trả về chứa `dry_run_mode`, `applied_payload` (với `aws_cli_command`) và `rollback_payload` (với `aws_cli_rollback_command` và `boto3_equivalent`), cùng với các quy tắc truy cập dựa trên nhóm Cognito và tiêu đề `X-Containment-Status: LOCKED` nếu tỷ lệ rollback của tenant vi phạm ngưỡng.
- **Kiểm thử Hành động Hoàn tác (Rollback Action Test)**: Mô phỏng việc kích hoạt hoàn tác thủ công trên bảng điều khiển bằng cách gọi endpoint rollback (đại diện cho ngữ nghĩa `POST /v1/audit/{audit_id}/rollback`). Kiểm thử xác minh rằng:
  - Hàm xử lý xác thực quyền hạn, email `rolled_back_by` và khớp `X-Tenant-Id`.
  - Nó khởi tạo rollback thành công, trả về `audit_recorded = true` (thay vì `rollback_initiated = true`), cập nhật bộ đếm số lỗi sai (false positive count) và tính toán lại tỷ lệ hao hụt ngân sách lỗi (`new_error_budget_burned_pct`).
  - Trạng thái sự kiện được ghi vào nhật ký kiểm toán dưới dạng `ROLLED_BACK`.
- **Kiểm thử Cache & Dự phòng Ngoại tuyến Hoàn tác (Rollback Caching & Offline Fallback Test)**: Xác minh rằng CDO backend thực hiện lưu cache cấu hình `rollback_payload.boto3_equivalent` vào bảng DynamoDB `finops-rollback-cache`. Thử nghiệm giả lập tình huống AI Engine ngoại tuyến/không thể kết nối và xác minh rằng CDO backend thực hiện rollback thành công thông qua các cuộc gọi Boto3 tiêu chuẩn bằng cấu hình đã lưu cache, sau đó báo cáo kết quả thực thi lên endpoint kiểm toán hoàn tác.
- **Kiểm thử Khóa ngân sách lỗi (Error Budget Lock Tests)**: Khẳng định rằng hành vi khóa containment (hiển thị banner `LOCKED_MODE` và vô hiệu hóa các hành động tự động) sẽ được kích hoạt ở tỷ lệ rollback >=1% đối với môi trường sản xuất (prod), >=10% đối với môi trường staging, và không bao giờ kích hoạt (bị vô hiệu hóa) trên các môi trường dev/sandbox, sử dụng lý do khóa là `error_budget_exceeded_threshold`.

### 4.10 Kiểm thử Mã lỗi & Xác thực Hợp đồng (Contract Error Codes & Validation Tests)

- **Xung đột Idempotency (Ngữ nghĩa `409` & `400`)**:
  - **Lượt gọi đang chạy (Ngữ nghĩa `409 Conflict`)**: Gọi Lambda của AI Engine với khóa idempotency đang hoạt động sẽ trả về cấu trúc phản hồi xung đột (đại diện cho ngữ nghĩa HTTP `409`) và ngăn thực thi trùng lặp.
  - **Lệch Payload (Ngữ nghĩa `400 Bad Request`)**: Gửi lại yêu cầu với khóa idempotency đã tồn tại nhưng payload khác biệt sẽ trả về cấu trúc phản hồi không khớp (đại diện cho ngữ nghĩa HTTP `400` với mã lỗi `ERR_IDEMPOTENCY_MISMATCH`).
- **Hạn chế Truy cập Multi-Tenant (Ngữ nghĩa `403 Forbidden`)**: Các yêu cầu truy vấn kết quả hoặc kích hoạt hành động với `X-Tenant-Id` không khớp sẽ bị chặn ngay lập tức với cấu trúc từ chối truy cập (đại diện cho ngữ nghĩa HTTP `403` / `ERR_CROSS_TENANT_DENIED`).
- **Dự phòng Timeout Bedrock (Bedrock Timeout Fallback)**: Khi cuộc gọi Bedrock giả lập vượt quá timeout cứng 45 giây, hệ thống xác nhận Lambda của AI Engine tự hủy tác vụ và trả về trạng thái `failed` cùng mã lỗi `ERR_LLM_TIMEOUT`. CDO bắt lỗi thất bại này và chuyển ngay sang rules engine tĩnh dự phòng.
- **Kiểm thử Độ lệch đồng hồ & Dấu thời gian đo lường (Clock Skew & Telemetry Timestamp Tests)**:
  - **Từ chối lệch đồng hồ yêu cầu (Request Clock Skew Reject)**: Xác minh rằng các yêu cầu có độ lệch thời gian API request timestamp drift (clock skew) lớn hơn 300 giây sẽ bị từ chối với mã lỗi `ERR_REPLAY_DETECTED`.
  - **Chấp nhận trễ dữ liệu CUR (CUR Data Lag Accept)**: Xác nhận rằng dữ liệu CUR có độ trễ dấu thời gian thu nhận lên tới 36 giờ vẫn được chấp nhận và xử lý thành công, vì nó nằm trong giới hạn trễ hóa đơn hàng ngày dự kiến.

### 4.11 Kiểm thử lịch trình thử lại callback (Callback retry schedule tests)

- **Xác minh Khoảng thời gian thử lại (Retry Interval Verification)**: Xác thực rằng khi việc truyền tải callback thất bại, nền tảng sẽ thực hiện lịch trình thử lại sau các khoảng trễ 0 giây, 30 giây, và 120 giây.
- **Cô lập lỗi & Ghi nhật ký (Fault Isolation & Logging)**: Xác minh rằng nếu vượt quá giới hạn số lần thử lại, sự kiện sẽ được ghi nhận là `CALLBACK_EXHAUSTED` trong dữ liệu đo lường vận hành của hệ thống, nhưng lượt chạy phát hiện đồng bộ chính không bị báo lỗi hoặc bị hủy bỏ.

---

## 5. Các kiểm thử cảnh báo và containment (Alert and containment tests)

### 5.1 Định tuyến cảnh báo (Alert routing)

- **Financial Routing**: Các sai lệch chi phí trên 100 USD/ngày được định tuyến đến Finance SNS topic.
- **Engineering Routing**: Chi tiết kỹ thuật bao gồm ID tài nguyên, tên dịch vụ và trạng thái vi phạm tag được định tuyến đến Slack webhook cụ thể của squad.
- **Payload Verification**: Đảm bảo rằng các chi tiết chi phí nhạy cảm được thể hiện bằng các tham chiếu S3/dashboard trong các thông báo Slack bên ngoài thay vì nhúng trực tiếp các bảng thô.

### 5.2 Containment ở chế độ giả lập (Containment dry-run)

- **Dry-run Execution**: Trong môi trường prod và staging, containment engine được khóa ở chế độ dry-run.
- **Resource Verification**: Xác minh rằng tài nguyên AWS mục tiêu vẫn không bị sửa đổi.
- **Dashboard Output**: Kiểm tra xem bảng điều khiển có hiển thị hành động dưới dạng "Được đề xuất" hoặc "Đã hoàn thành dry-run" hay không.

### 5.3 Ghi bản ghi kiểm toán (Audit log write)

Containment engine phải tạo một mục nhật ký kiểm toán cho mỗi lần thử hành động. Kiểm thử này xác minh rằng schema JSON được ghi chứa đầy đủ 15 trường bắt buộc:
1. `actor`: Thực thể thực hiện hành động (ví dụ: `cdo-platform-orchestrator`).
2. `timestamp`: Dấu thời gian thực thi theo chuẩn UTC.
3. `correlation_id`: Định danh duy nhất theo dõi lượt chạy cụ thể.
4. `idempotency_key`: Khóa ngăn chặn thực thi kép (dạng composite `{tenant_id}:{billing_period_date}:{batch_type}`).
5. `anomaly_id`: ID tham chiếu của bất thường được phát hiện.
6. `resource_owner`: Nhóm/squad chịu trách nhiệm về tài nguyên.
7. `resource_id`: ARN AWS của tài nguyên mục tiêu.
8. `before_state`: Đối tượng chi tiết chứa cấu hình/tag tài nguyên trước khi thực hiện hành động.
9. `proposed_after_state`: Trạng thái tài nguyên dự kiến sau khi áp dụng containment.
10. `execution_mode`: Giá trị đại diện cho `dry-run` hoặc `apply`.
11. `rollback_path`: Cấu trúc xác định các bước chính xác cần thiết để hoàn tác hành động.
12. `approval_status`: Trạng thái phê duyệt (ví dụ: `pending_approval`, `approved`, `bypassed`).
13. `retention_location`: URI S3 nơi bản ghi được lưu trữ.
14. `retention_period_days`: Số đại diện cho thời gian lưu trữ (phải >= 90 ngày).
15. `audit_chain`: Cấu trúc lưu chuỗi băm kiểm toán chống giả mạo gồm `event_hash` (`sha256(current_payload + previous_hash)`) và `previous_hash` của sổ cái kiểm toán.

### 5.4 Xác thực Dashboard & Xác minh Nhóm Cognito (Dashboard Auth & Cognito Group Validation)

- **Kiểm thử Chuyển hướng Hosted UI (Hosted UI Redirection Test)**: Xác minh rằng bất kỳ yêu cầu truy cập chưa được xác thực nào tới URL dashboard CloudFront đều bị chặn bởi lớp bảo mật Lambda@Edge và được chuyển hướng (redirect 302) đến endpoint đăng nhập của Cognito Hosted UI.
- **Kiểm thử Quyền chỉ đọc của Nhóm Finance (Finance Group Read-Only Access Test)**: Xác thực rằng người dùng thuộc nhóm người dùng Cognito `finops-finance-readonly` được xác thực thành công nhưng bị giới hạn ở các chế độ xem chỉ đọc trên dashboard. Các yêu cầu thực hiện hành động ngăn chặn (Xác thực hoặc Khôi phục) qua các yêu cầu POST gửi tới `/v1/verify` hoặc `/v1/audit/{audit_id}/rollback` đều bị từ chối với lỗi HTTP `403 Forbidden` / `ERR_CROSS_TENANT_DENIED` hoặc `ERR_AUTH_FAILED`.
- **Kiểm thử Phân quyền Hành động của Nhóm Engineering (Engineering Group Action Authorization Test)**: Xác minh rằng người dùng trong các nhóm `finops-engineering-operator` và `finops-cdo-admin` có thể kích hoạt thành công các hành động Xác thực/Khôi phục (Verification/Rollback) trên dashboard, xác nhận các mã JWT chứa đúng các thông tin nhóm (group claims) khi chuyển tiếp đến các endpoint API hành động.
- **Kiểm thử Hết hạn Phiên & Thời gian tồn tại của Token (Session Expiration & Token Lifetime Test)**: Xác thực rằng các phiên làm việc đã hết hạn (mã JWT cũ hơn thời gian cấu hình 15 phút) hoặc các chữ ký cookie JWT bị sửa đổi sẽ bị Lambda@Edge từ chối, lập tức chấm dứt phiên làm việc và chuyển hướng người dùng đăng nhập lại.
- **Ghi nhật ký Kiểm toán cho Sự kiện Auth (Audit Logging for Auth Events)**: Xác nhận rằng các sự kiện đăng nhập/đăng xuất, lỗi xác thực mã token và các nỗ lực thực hiện hành động trái phép (ví dụ: người dùng Finance cố gắng khôi phục) đều được ghi nhận vào nhật ký kiểm toán trên S3 (ví dụ: ghi lại trạng thái `auth_success`, `auth_failure`, hoặc `unauthorized_action_blocked`).

---

## 6. Kịch bản demo E2E (E2E demo scenario)

Bản demo End-to-End chứng minh toàn bộ quy trình thu thập, phát hiện, cảnh báo và containment:
- **Bước 1 - Chèn dữ liệu (Step 1 - Injection)**: Các bản ghi chi phí không được quản lý giả lập (ví dụ: chi tiêu 500 USD trên các instance EC2 g5.4xlarge) được ghi vào S3 bucket của CUR.
- **Bước 2 - Kích hoạt (Step 2 - Trigger)**: EventBridge kích hoạt luồng công việc thu thập dữ liệu của Step Functions.
- **Bước 3 - Gọi Lambda (Step 3 - Lambda Invocation)**: Luồng công việc thu thập dữ liệu trích xuất các bản ghi chi phí và gọi endpoint ALB nội bộ riêng tư của AI Engine một cách đồng bộ qua HTTPS và SigV4, hàm này trả về chỉ thị phát hiện thành công và danh sách các bất thường.
- **Bước 4 - Thực thi tác vụ (Step 4 - Task Execution)**: Luồng công việc Step Functions xử lý dữ liệu chi phí, ghi lại kết quả bất thường/audit vào kho lưu trữ có thẩm quyền S3 (với việc cache trên DynamoDB để hiển thị bảng điều khiển), và lưu trữ tài liệu chứng cứ lập luận chi tiết vào S3.
- **Bước 5 - Cập nhật bảng điều khiển (Step 5 - Dashboard Update)**: Lambda tổng hợp kết quả, ghi các tệp JSON đã cập nhật vào S3 bucket của bảng điều khiển và kích hoạt invalidation trên CloudFront.
- **Bước 6 - Định tuyến cảnh báo (Step 6 - Alert Routing)**: Alert Routing Lambda được gọi, gửi thông báo Slack đến kênh `squad-prediction-models` và thông báo email đến nhóm Finance qua SNS/SES.
- **Bước 7 - Containment giả lập (Step 7 - Dry-run Containment)**: Containment engine của CDO kích hoạt cập nhật tag dry-run (`FinOpsWatch: ReviewRequired`) và lưu bản ghi kiểm toán chứa các bước rollback vào S3.
- **Bước 8 - Giả lập hoàn tác (Step 8 - Rollback Simulation)**: Quản trị viên nhấp vào nút "Rollback" trên bảng điều khiển CDO, kích hoạt endpoint rollback (đại diện cho ngữ nghĩa `POST /v1/audit/{audit_id}/rollback`), bắt đầu khôi phục lại tag của tài nguyên chéo tài khoản bằng cách thực thi payload `rollback_payload.boto3_equivalent` đã được cache trong bảng DynamoDB `finops-rollback-cache` và cập nhật số liệu đo lường về ngân sách lỗi.

---

## 7. Kiểm thử bảo mật (Security test)

### 7.1 Các điểm thâm nhập thử nghiệm (Penetration touch points)

- **S3 Bucket Access Control**: Các thử nghiệm xác minh rằng S3 bucket của CUR và S3 bucket của nhật ký kiểm toán từ chối tất cả các yêu cầu bắt nguồn từ bên ngoài VPC endpoint policies và các vai trò IAM được chỉ định.
- **Lambda Invocation Isolation**: Xác minh rằng việc gọi trực tiếp hàm Lambda của AI Engine bị chặn đối với bất kỳ danh tính IAM nào thiếu quyền `lambda:InvokeFunction` rõ ràng.
- **Containment IAM Restrictions**: Xác minh rằng các role execution Lambda được sử dụng cho các hành động containment bị chặn không cho phép sửa đổi các chính sách IAM, xóa dữ liệu S3 hoặc tắt các khối lượng công việc sản xuất quan trọng.

### 7.2 Quét lỗ hổng bảo mật (Vulnerability scan)

- **ECR Container Scanning**: Các hình ảnh Lambda container được quét trên ECR trong pipeline CI/CD bằng tính năng quét gốc của AWS.
- **Remediation**: Việc triển khai bị chặn nếu phát hiện bất kỳ lỗ hổng CRITICAL hoặc HIGH nào trong môi trường chạy container hoặc các phụ thuộc.
- **Audit Trails**: Nhật ký quét bảo mật được lưu trữ cùng với lịch sử pipeline triển khai.

---

## 8. Phân tích lỗi (Failure analysis)

### 8.1 Các lỗi đã gặp phải (Failures encountered)

Bảng sau tóm tắt các lỗi đã được giải quyết trong các giai đoạn kiểm thử:

| STT (No.) | Lỗi gặp phải (Failure Encountered) | Nguyên nhân gốc (Root Cause) | Biện pháp khắc phục (Fix / Resolution) | Thời gian khắc phục (Giờ) (Time to Fix (Hours)) |
|---|---|---|---|---|
| 1 | CUR Schema Mismatch | AWS cập nhật cấu trúc xuất dữ liệu CUR thanh toán, thêm các cột mới. | Sửa đổi cấu hình phân tích cú pháp schema của Glue để xử lý các schema động. | 6 |
| 2 | Lambda Cold Start Timeout | Việc khởi tạo container Lambda mất nhiều thời gian hơn giới hạn timeout của client. | Cấu hình SQS để xử lý không đồng bộ (async), tránh bị timeout của client. | 3 |
| 3 | Slack Webhook Rate Limit | Nhiều cảnh báo bất thường trùng lặp đã kích hoạt giới hạn tần suất của Slack. | Triển khai gom nhóm và xử lý hàng loạt cảnh báo trong Lambda định tuyến. | 8 |

### 8.2 Các lỗ hổng kiểm thử được thừa nhận (Test gaps acknowledged)

Do các hạn chế về môi trường, các kịch bản kiểm thử sau chưa được xác minh với hạ tầng sản xuất thực tế:
- **Cross-Account Ingestion Scale**: Thu thập dữ liệu chi phí trên hơn 50 tài khoản AWS đồng thời. (Cần bằng chứng: thiết lập môi trường staging đa tài khoản đang chờ xử lý)
- **Lambda Concurrency Exhaustion under Peak Load**: Xác minh giới hạn concurrency của Lambda khi có tải chạy song song của nhiều tenant lớn. (Cần bằng chứng: các kiểm thử giả lập concurrency đang chờ xử lý)
- **Production Containment Policy Impact**: Thực thi các hành động chính sách ở chế độ apply trong môi trường sản xuất trực tiếp. (Cần bằng chứng: sự phê duyệt của ban tuân thủ đang chờ xử lý)

---

## Tài liệu liên quan (Related documents)

- [`02_infra_design_vi.md`](02_infra_design_vi.md) - Chi tiết các bảng thành phần, sơ đồ kiến trúc tổng thể và sơ đồ bảo mật mạng.
- [`03_security_design_vi.md`](03_security_design_vi.md) - Chi tiết các vai trò dịch vụ IAM, mã hóa dữ liệu khi lưu trữ (encryption at rest), mã hóa dữ liệu khi truyền tải (encryption in transit) và cấu hình nhật ký kiểm toán chi tiết.
- [`08_adrs_vi.md`](08_adrs_vi.md) - Giải thích các quyết định kiến trúc bao gồm chu kỳ 24 giờ, containment ưu tiên giả lập (dry-run-first) và các lựa chọn Private API Gateway và hosting Lambda.
