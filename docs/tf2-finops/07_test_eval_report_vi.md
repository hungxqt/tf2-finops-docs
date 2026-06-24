# Báo cáo Kiểm thử và Đánh giá (Test & Eval Report) - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Refined (W12 T4 Pack #2)
-->

## 1. Phạm vi kiểm thử (Test coverage)

Việc xác minh nền tảng FinOps Watch CDO được thực hiện trên nhiều cấp độ kiểm thử khác nhau nhằm đảm bảo tính toàn vẹn của hoạt động vận hành, sự tuân thủ nghiêm ngặt đối với hợp đồng AI Engine do nhóm AIOps cung cấp, và các hành vi containment an toàn.

| Loại kiểm thử (Test Type) | Công cụ (Tool) | Phạm vi / Mô tả (Scope / Description) |
|---|---|---|
| Unit | pytest | Xác thực các Lambda handlers riêng lẻ viết bằng Python, các hàm tiện ích, các hàm hỗ trợ tính toán chi phí và các adapter dữ liệu. |
| Integration | AWS SDK mock (boto3 mock / moto), pytest | Xác minh các hoạt động ghi S3, đọc/ghi DynamoDB, xử lý hàng đợi SQS và gửi thông báo SNS/SES. |
| E2E (End-to-End) | Custom test harnesses, CLI scripts | Thực thi toàn bộ luồng dữ liệu từ việc chèn bất thường giả lập trong CUR, lập lịch, gọi AI Engine, cập nhật cơ sở dữ liệu, cho đến định tuyến cảnh báo và dry-run đối với containment. |
| Scheduled-Run Idempotency | Custom test scripts | Xác nhận rằng việc xử lý cùng một chu kỳ thanh toán CUR hai lần không tạo ra các bản ghi trùng lặp trong cơ sở dữ liệu hoặc kích hoạt các hành động cảnh báo/containment trùng lặp. |
| Chaos / Failure | AWS Fault Injection Service (FIS) | Giả lập các phân vùng mạng, giới hạn tần suất gọi API (throttling) của Cost Explorer API, độ trễ cơ sở dữ liệu và tình trạng AI Engine không khả dụng để xác minh các đường dẫn fail-closed và phục hồi mềm dẻo. |

---

## 2. Bằng chứng SLO (SLO evidence)

Hiệu suất vận hành của nền tảng được đánh giá dựa trên các Mục tiêu Mức độ Dịch vụ (SLOs) được thiết lập cho độ tin cậy, độ tươi mới của dữ liệu và tốc độ truyền tải thông tin.

| SLO | Mục tiêu (Target) | Đã đo lường (Measured) | Chu kỳ đánh giá (Window) | Đạt/Không đạt (Pass/Fail) |
|---|---|---|---|---|
| Scheduled Run Success Rate | >=99.9% số lần chạy hàng ngày được lập lịch | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý | 30 ngày (30 Days) | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý |
| Data Freshness | <=24 giờ từ khi CUR khả dụng đến Athena | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý | Chu kỳ hàng ngày (Daily Cycle) | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý |
| Dashboard Refresh Latency | <=5 phút từ khi pipeline hoàn thành đến khi cập nhật tài nguyên tĩnh | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý | Chu kỳ hàng ngày (Daily Cycle) | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý |
| Alert Delivery Latency | <=30 phút từ khi phát hiện bất thường đến khi gửi tới Slack/SNS | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý | Theo từng cảnh báo (Per-Alert) | Cần bằng chứng: số liệu chạy sản xuất đang chờ xử lý |

### 2.1 Các SLO tích hợp theo hợp đồng (AI Engine API)

Việc tuân thủ các giới hạn bắt buộc theo hợp đồng từ `ai-api-contract.md` §6 được đo lường theo chương trình:

| Chỉ số SLO hợp đồng | Mục tiêu | Điểm đo lường | Kết quả xác minh |
|---|---|---|---|
| Độ trễ Ingestion (P99) | < 50 ms | Độ trễ phản hồi POST `/v1/detect` | Cần bằng chứng: đo lường tích hợp API đang chờ xử lý |
| Độ trễ truy vấn kết quả (P99) | < 10 ms | Độ trễ phản hồi GET `/v1/detect/result/{audit_id}` | Cần bằng chứng: đo lường tích hợp API đang chờ xử lý |
| SLA suy luận LLM | < 30 giây | Thời gian chạy logic suy luận bất tuần tự | Cần bằng chứng: đo lường tích hợp API đang chờ xử lý |
| Tính khả dụng hệ thống | >=99.5% | Tỷ lệ thành công của health check API ALB | Cần bằng chứng: số liệu thời gian hoạt động của ALB |
| Tỷ lệ lỗi | < 0.5% | Số phản hồi HTTP 5xx / tổng số yêu cầu | Cần bằng chứng: đo lường tích hợp API đang chờ xử lý |

### 2.2 Phân tích vi phạm SLO (SLO breach analysis)

Trong trường hợp xảy ra vi phạm SLO, các quy trình leo thang và khắc phục sau sẽ được kích hoạt:
- **Cost Explorer Throttling**: Nếu vượt quá giới hạn tần suất gọi API của Cost Explorer API, Lambda thu thập dữ liệu sẽ bắt lấy ngoại lệ và thử lại bằng chiến lược exponential backoff. Nếu lượt chạy vượt quá cửa sổ SLA 24 giờ, nhóm vận hành sẽ được cảnh báo qua PagerDuty.
- **AI Engine Container Startup Timeouts**: Nếu các tác vụ container Fargate Spot không khởi động được hoặc gặp độ trễ lớn khi cấp phát tài nguyên trong các sự kiện mở rộng quy mô cao điểm, nền tảng sẽ tự động chuyển việc xử lý yêu cầu sang các tác vụ capacity provider Fargate luôn hoạt động (always-on) để duy trì SLO về độ trễ.
- **S3 / CloudFront Invalidation Delays**: Nếu các bản cập nhật JSON của dashboard không phân phối được do hành vi bộ nhớ đệm của CloudFront, API invalidation sẽ tự động được thử lại bởi pipeline triển khai trang web tĩnh.

---

## 3. Các kiểm thử nền tảng CDO (CDO platform tests)

### 3.1 Thu thập dữ liệu (Data ingestion)

Xác minh Thu thập dữ liệu (Data Ingestion) tập trung vào việc lấy và phân tích cú pháp dữ liệu chi phí từ AWS Data Exports (CUR 2.0) và AWS Cost Explorer API:
- **Raw Ingestion**: Lambda thu thập dữ liệu thô lấy các tệp parquet/CSV từ S3 bucket thanh toán và xác minh rằng các định nghĩa schema khớp với cấu trúc đã xác định.
- **Cost Explorer Queries**: Xác minh rằng các phản hồi giả lập từ Cost Explorer API khớp với các kỳ vọng lịch sử và được ánh xạ tới các cửa sổ chi phí được chuẩn hóa.
- **Glue Crawler & Athena Views**: Các kiểm thử xác minh rằng Glue Crawler biên mục thành công cấu trúc phân vùng raw trên S3 và các truy vấn Athena có thể tổng hợp các chỉ số chi phí theo dịch vụ, khu vực, tài khoản và các tag tài nguyên mà không gặp lỗi cú pháp. Dưới thiết kế telemetry CUR-only, tuyệt đối không có metric hiệu năng CloudWatch (CPU, memory, database connections) nào được thu thập hoặc gửi sang AI Engine phục vụ phát hiện bất thường. Các tín hiệu hiệu năng được kiểm chứng chỉ sử dụng riêng cho mục đích giám sát sức khỏe vận hành của CDO platform (cảnh báo, logging, dashboard).

### 3.2 Tính không thay đổi của lượt chạy theo lịch trình (Scheduled run idempotency)

Pipeline chạy theo một chu kỳ được lập lịch (ADR-001) được kích hoạt bởi EventBridge Scheduler. Để xác minh tính không thay đổi (idempotency):
- **Duplicate Execution Test**: Cùng một phân vùng cửa sổ ngày (ví dụ: 2026-06-22) được gửi hai lần đến luồng công việc thu thập dữ liệu.
- **State Check**: Step Functions kiểm tra xem cơ sở dữ liệu trạng thái thực thi (DynamoDB) đã có bản ghi cho `idempotency_key` hay chưa (được định dạng là `AccountID:DateWindow`).
- **Execution Bypass**: Lượt chạy thứ hai được bỏ qua một cách thành công, và không có bản ghi trùng lặp nào trong cơ sở dữ liệu hay tin nhắn cảnh báo nào được tạo ra.

### 3.3 Làm mới bảng điều khiển (Dashboard refresh)

- **Static Asset Generation**: Một tác vụ Lambda chuyên dụng được thực thi sau khi luồng công việc thu thập dữ liệu kết thúc để tổng hợp và ghi các tệp JSON chứa tóm tắt chi tiêu vào S3 bucket của bảng điều khiển công khai.
- **Frontend Verification**: Kịch bản kiểm thử giả lập một trình duyệt máy khách lấy các cấu trúc JSON đã cập nhật và xác nhận rằng các biểu đồ cập nhật chính xác để phản ánh các điểm chi phí mới.

---

## 4. Các kiểm thử tích hợp AI (AI integration tests)

### 4.1 Hợp đồng AI (AI contract)

Giao diện dựa trên hợp đồng giữa nền tảng CDO và AI Engine (do AIOps sở hữu) được xác minh về tính tuân thủ schema nghiêm ngặt:
- **Request Format Verification**: Trình kiểm thử gửi các yêu cầu tuân thủ schema phiên bản `telemetry://finops-watch/v3` chứa các header `X-Tenant-Id`, `X-Idempotency-Key` (composite key: `tenant_id:YYYY-MM-DD`), `X-Correlation-Id`, `X-Payload-SHA256`, và `X-Request-Timestamp` tới endpoint dùng chung (`https://ai-engine.tf-2.internal/`) sử dụng xác thực IAM SigV4. Kiểm thử xác minh rằng payload yêu cầu là CUR-only (kiểu `RAW_JSON` hoặc `S3_POINTER`) và hoàn toàn không chứa metric hiệu năng CloudWatch.
- **Response Format Verification**: Kiểm thử xác minh rằng AI Engine trả về phản hồi chứa các tham số bắt buộc: `audit_id`, `status` (`completed` | `processing` | `failed`), mảng `anomalies_list` (chứa `anomaly_metadata`, `finance_dashboard_data` và `engineering_dashboard_data`) và cấu trúc phân trang `pagination` (`next_token` và `limit`).

### 4.2 Hết thời gian chờ AI Engine (AI Engine timeout)

- **Timeout Simulation**: Một tác vụ container giả lập được cấu hình để trì hoãn phản hồi thêm 30 giây (vượt quá thời gian chờ 15 giây của máy khách).
- **Execution**: CDO client gọi API.
- **Verification**: Nền tảng CDO phát hiện hết thời gian chờ, dừng yêu cầu, ghi lại cảnh báo và thử lại tối đa 3 lần trước khi leo thang.

### 4.3 Cơ chế dự phòng khi AI không khả dụng (Unavailable-AI fallback)

Nếu AI Engine hoàn toàn không thể truy cập được (ví dụ: lỗi HTTP 503, ALB gateway timeout, hoặc cạn kiệt tài nguyên cụm Fargate):
- **Fail Closed Behavior**: Nền tảng CDO ngay lập tức hủy bỏ mọi kích hoạt hành động containment theo lịch trình. Không áp dụng chính sách tự động nào.
- **Operator Alert**: Một ticket sự cố nghiêm trọng và cảnh báo PagerDuty được định tuyến đến các nhóm kỹ thuật và tài chính CDO trung tâm.
- **Audit Logging**: Một bản ghi lỗi được ghi vào S3 bucket kiểm toán, chi tiết hóa tình trạng không khả dụng của AI Engine.

### 4.4 Cấu hình/vị trí tác vụ ECS (ECS task configuration/placement)

- **Capacity Provider Placement**: Kịch bản xác minh kiểm tra cấu hình triển khai tác vụ ECS đang hoạt động trong môi trường mục tiêu.
- **Always-on Services**: Xác nhận rằng các API servers, tác vụ giám sát và internal ALB được đặt trên các capacity provider Fargate luôn hoạt động (always-on) để xử lý lưu lượng thời gian thực.
- **Batch Services**: Xác nhận rằng các tác vụ xử lý hàng loạt (batch), feature engineering và huấn luyện mô hình được gán cho các capacity provider Fargate Spot.

### 4.5 Gián đoạn và thử lại Fargate Spot (Fargate Spot interruption/retry)

- **Interruption Mocking**: Một sự kiện giả lập ECS Task Interruption Event được gửi đến ECS Cluster.
- **SQS Queue Durability**: Xác minh rằng yêu cầu hàng loạt đang hoạt động không bị mất và được trả lại hàng đợi SQS.
- **Task Retry**: Xác minh rằng bộ lập lịch tác vụ khởi chạy một container thay thế và tiếp tục xử lý từ checkpoint cuối cùng được lưu trữ trong S3.

### 4.6 Tính khả dụng của API (API availability)

- **ALB Ingress Verification**: Thử nghiệm endpoint ALB nội bộ (`/health`) từ bên trong mạng con riêng tư (private subnet).
- **Metrics**: Thời gian phản hồi phải duy trì dưới 100 mili giây đối với các cuộc gọi kiểm tra sức khỏe đơn giản.

### 4.7 Tự động mở rộng quy mô (Autoscaling)

- **Load Simulation**: Lưu lượng truy cập đồng thời cao được hướng tới explainer endpoint.
- **AWS Application Auto Scaling**: Xác minh rằng việc sử dụng CPU kích hoạt việc thêm tác vụ lên đến giới hạn cấu hình, và giảm số lượng tác vụ khi tải lưu lượng giảm.

### 4.8 Kiểm thử Thăm dò và Phân trang API (API Result Polling & Pagination Tests)

- **Xác thực Phản hồi Polling**: Khung kiểm thử truy vấn GET `/v1/detect/result/{audit_id}` để xác minh các trạng thái phản hồi của hợp đồng (`completed` vs. `processing` vs. `failed`) và xác thực cấu trúc của đối tượng `anomalies_list`.
- **Xác thực Phân trang**: Dưới tải kiểm thử tạo ra nhiều bất thường, khung kiểm thử yêu cầu kết quả với `limit=1` và xác minh `next_token` được tạo. Sau đó, nó truy vấn các trang tiếp theo bằng token này, xác nhận thứ tự index kết quả chính xác.

### 4.9 Kiểm thử Endpoint Gia hạn & Hoàn tác (Extend & Rollback Endpoints Tests)

- **Kiểm thử API Gia hạn (Extend/Snooze)**: Mô phỏng hành động của kỹ sư bằng cách POST tới `/v1/action/extend` với `extend_seconds` và `reason`. Kiểm thử xác minh API cập nhật bộ đếm thời gian countdown của tài nguyên và trả về `new_expiration_time`.
- **Kiểm thử API Hoàn tác (Rollback)**: Mô phỏng việc nhấp vào "Revert" trên bảng điều khiển bằng cách gọi POST `/v1/action/rollback`. Kiểm thử xác minh rằng:
  - API kiểm tra xác thực và khớp `X-Tenant-Id`.
  - Nó tạo và trả về thành công lệnh CLI khôi phục bắt buộc (ví dụ: `aws rds start-db-instance`).
  - Trạng thái sự kiện được ghi vào nhật ký kiểm toán dưới dạng `rollback_initiated`.

### 4.10 Kiểm thử Mã lỗi & Xác thực Hợp đồng (Contract Error Codes & Validation Tests)

- **Trùng Khóa Idempotency (`409` & `400`)**:
  - **Lượt gọi đang chạy (`409 Conflict`)**: Gửi yêu cầu với khóa idempotency đang hoạt động sẽ trả về HTTP `409` và ngăn thực thi trùng lặp.
  - **Lệch Payload (`400 Bad Request`)**: Gửi lại yêu cầu với khóa idempotency đã tồn tại nhưng payload khác biệt sẽ trả về HTTP `400` với mã lỗi `ERR_IDEMPOTENCY_MISMATCH`.
- **Hạn chế Truy cập Multi-Tenant (`403 Forbidden`)**: Các yêu cầu gọi GET `/v1/detect/result/{audit_id}` với `audit_id` thuộc về một `X-Tenant-Id` khác sẽ bị chặn ngay lập tức với mã HTTP `403` / `ERR_CROSS_TENANT_DENIED`.
- **Dự phòng Timeout Bedrock (`500 Internal Error`)**: Khi cuộc gọi Bedrock giả lập vượt quá timeout cứng 45 giây, hệ thống xác nhận AI Engine tự hủy tác vụ và ghi trạng thái `failed` vào DB. CDO polling bắt lỗi HTTP `500` / `ERR_LLM_TIMEOUT` và chuyển ngay sang Rules Engine tĩnh dự phòng.

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
4. `idempotency_key`: Khóa ngăn chặn thực thi kép (dạng composite `tenant_id:YYYY-MM-DD`).
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

---

## 6. Kịch bản demo E2E (E2E demo scenario)

Bản demo End-to-End chứng minh toàn bộ quy trình thu thập, phát hiện, cảnh báo và containment:
- **Bước 1 - Chèn dữ liệu (Step 1 - Injection)**: Các bản ghi chi phí không được quản lý giả lập (ví dụ: chi tiêu 500 USD trên các instance EC2 g5.4xlarge) được ghi vào S3 bucket của CUR.
- **Bước 2 - Kích hoạt (Step 2 - Trigger)**: EventBridge kích hoạt luồng công việc thu thập dữ liệu của Step Functions.
- **Bước 3 - Gọi API (Step 3 - API Invocation)**: Luồng công việc thu thập dữ liệu trích xuất các bản ghi chi phí, gọi endpoint ALB nội bộ của AI Engine API và nhận phản hồi phân loại bất thường.
- **Bước 4 - Thực thi tác vụ (Step 4 - Task Execution)**: Tác vụ container AI Engine xử lý các đặc trưng, ghi lại bất thường vào DynamoDB và lưu trữ lập luận chi tiết.
- **Bước 5 - Cập nhật bảng điều khiển (Step 5 - Dashboard Update)**: Lambda tổng hợp kết quả, ghi các tệp JSON đã cập nhật vào S3 bucket của bảng điều khiển và kích hoạt invalidation trên CloudFront.
- **Bước 6 - Định tuyến cảnh báo (Step 6 - Alert Routing)**: Alert Routing Lambda được gọi, gửi thông báo Slack đến kênh `squad-prediction-models` và thông báo email đến nhóm Finance qua SNS/SES.
- **Bước 7 - Containment giả lập (Step 7 - Dry-run Containment)**: Containment engine của CDO kích hoạt cập nhật tag dry-run (`FinOpsWatch: ReviewRequired`) và lưu bản ghi kiểm toán chứa các bước rollback vào S3.
- **Bước 8 - Giả lập hoàn tác (Step 8 - Rollback Simulation)**: Quản trị viên nhấp vào nút "Revert" trên bảng điều khiển CDO, thực thi các bước rollback được xác định trong bản ghi kiểm toán để đưa các tag trở lại trạng thái baseline ban đầu.

---

## 7. Kiểm thử bảo mật (Security test)

### 7.1 Các điểm thâm nhập thử nghiệm (Penetration touch points)

- **S3 Bucket Access Control**: Các thử nghiệm xác minh rằng S3 bucket của CUR và S3 bucket của nhật ký kiểm toán từ chối tất cả các yêu cầu bắt nguồn từ bên ngoài VPC endpoint policies và các vai trò IAM được chỉ định.
- **ECS Network Isolation**: Xác minh rằng các yêu cầu ingress trực tiếp đến các tác vụ AI Engine từ mạng con công cộng (public subnets) hoặc internet gateways bị chặn bởi các quy tắc security group.
- **Containment IAM Restrictions**: Xác minh rằng các vai trò tác vụ Lambda/ECS được sử dụng cho các hành động containment bị chặn không cho phép sửa đổi các chính sách IAM, xóa dữ liệu S3 hoặc tắt các khối lượng công việc sản xuất quan trọng.

### 7.2 Quét lỗ hổng bảo mật (Vulnerability scan)

- **ECR Container Scanning**: Các hình ảnh container được quét trong pipeline CI/CD bằng tính năng quét gốc của AWS.
- **Remediation**: Việc triển khai bị chặn nếu phát hiện bất kỳ lỗ hổng CRITICAL hoặc HIGH nào trong môi trường chạy container hoặc các phụ thuộc.
- **Audit Trails**: Nhật ký quét bảo mật được lưu trữ cùng với lịch sử pipeline triển khai.

---

## 8. Phân tích lỗi (Failure analysis)

### 8.1 Các lỗi đã gặp phải (Failures encountered)

Bảng sau tóm tắt các lỗi đã được giải quyết trong các giai đoạn kiểm thử:

| STT (No.) | Lỗi gặp phải (Failure Encountered) | Nguyên nhân gốc (Root Cause) | Biện pháp khắc phục (Fix / Resolution) | Thời gian khắc phục (Giờ) (Time to Fix (Hours)) |
|---|---|---|---|---|
| 1 | CUR Schema Mismatch | AWS cập nhật cấu trúc xuất dữ liệu CUR thanh toán, thêm các cột mới. | Sửa đổi cấu hình phân tích cú pháp schema của Glue để xử lý các schema động. | 6 |
| 2 | ALB Health Check Timeout | Việc khởi tạo container AI Engine mất nhiều thời gian hơn ngưỡng health check. | Điều chỉnh khoảng thời gian grace period của target group health check từ 30 giây lên 90 giây. | 3 |
| 3 | Slack Webhook Rate Limit | Nhiều cảnh báo bất thường trùng lặp đã kích hoạt giới hạn tần suất của Slack. | Triển khai gom nhóm và xử lý hàng loạt cảnh báo trong Lambda định tuyến. | 8 |

### 8.2 Các lỗ hổng kiểm thử được thừa nhận (Test gaps acknowledged)

Do các hạn chế về môi trường, các kịch bản kiểm thử sau chưa được xác minh với hạ tầng sản xuất thực tế:
- **Cross-Account Ingestion Scale**: Thu thập dữ liệu chi phí trên hơn 50 tài khoản AWS đồng thời. (Cần bằng chứng: thiết lập môi trường staging đa tài khoản đang chờ xử lý)
- **Fargate Spot AWS Interruption Event Frequency**: Xác minh các sự kiện thu hồi Fargate Spot thực tế khi tải cụm cao. (Cần bằng chứng: dữ liệu giả lập thu hồi AWS Spot đang chờ xử lý)
- **Production Containment Policy Impact**: Thực thi các hành động chính sách ở chế độ apply trong môi trường sản xuất trực tiếp. (Cần bằng chứng: sự phê duyệt của ban tuân thủ đang chờ xử lý)

---

## Tài liệu liên quan (Related documents)

- [`02_infra_design_vi.md`](02_infra_design_vi.md) - Chi tiết các bảng thành phần, sơ đồ kiến trúc tổng thể và sơ đồ bảo mật mạng.
- [`03_security_design_vi.md`](03_security_design_vi.md) - Chi tiết các vai trò dịch vụ IAM, mã hóa dữ liệu khi lưu trữ (encryption at rest), mã hóa dữ liệu khi truyền tải (encryption in transit) và cấu hình nhật ký kiểm toán chi tiết.
- [`08_adrs_vi.md`](08_adrs_vi.md) - Giải thích các quyết định kiến trúc bao gồm chu kỳ 24 giờ, containment ưu tiên giả lập (dry-run-first) và các lựa chọn lưu trữ trên ECS.
