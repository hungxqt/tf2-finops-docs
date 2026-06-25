# Thiết kế Bảng điều khiển & Cảnh báo (Dashboard & Alerting Design) - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Refined (W12 T4 Pack #2)
-->

> [!IMPORTANT]
> **Ranh giới Bảo mật**: Mọi trạng thái hiển thị của bảng điều khiển và kiểm soát hành động containment phải tuân thủ nghiêm ngặt ranh giới cứng: **NEVER terminate prod, delete data, hoặc modify IAM**.


## 1. Tổng quan về bảng điều khiển (Dashboard overview)

Bảng điều khiển Tài chính (Finance Dashboard) cung cấp khả năng truy cập trực quan, không cần dùng SQL vào các xu hướng chi phí, phát hiện bất thường và lịch sử kiểm toán containment cho môi trường AWS của công ty.

### Mục đích (Purpose)
Thu hẹp khoảng cách giữa hoạt động vận hành hạ tầng kỹ thuật và sự giám sát tài chính. Bảng điều khiển trả lời bốn câu hỏi chính cho các bên liên quan của bộ phận Tài chính (Finance):
1. Có những thay đổi chi phí nào xảy ra và tác động của nó tới ngân sách là gì?
2. Tài khoản, dịch vụ hoặc squad nào sở hữu các tài nguyên bất thường đó?
3. Hệ thống có độ tin cậy bao nhiêu phần trăm đối với bất thường được phát hiện?
4. Hành động containment nào đã được đề xuất hoặc áp dụng?

### Đối tượng mục tiêu (Target Audience)
Đối tượng chính là các bên liên quan thuộc bộ phận Tài chính (CFO, quản lý tài chính) và các trưởng nhóm phát triển (squad leads), những người cần quản lý ngân sách đám mây của mình mà không cần đi sâu vào log thô hoặc giao diện kỹ thuật AWS console.

### Lựa chọn kiến trúc (Architecture Choice)
Finance Dashboard:
Một bảng điều khiển web nội bộ nhẹ được lưu trữ dưới dạng tài sản tĩnh trong Amazon S3 và phân phối qua Amazon CloudFront. Bảng điều khiển đọc các bản tóm tắt thân thiện với tài chính được tính toán trước từ các đối tượng S3 JSON (với DynamoDB đóng vai trò như một bộ nhớ cache đọc được tối ưu hóa cho dashboard giúp hiển thị nhanh chóng) được tạo ra bởi luồng công việc thu thập dữ liệu theo lịch trình của Step Functions. Athena vẫn hoạt động phía sau để tạo các bản tóm tắt được tinh lọc; người dùng Tài chính không bao giờ phải viết mã SQL.

QuickSight được giữ lại như một tùy chọn BI trong tương lai cho các nhóm Tài chính lớn hơn hoặc báo cáo ban điều hành, nhưng nó không phải là bảng điều khiển MVP mặc định vì capstone ưu tiên chi phí định kỳ thấp và không có phí seat cho mỗi reader BI.

### Kiểm soát truy cập Cognito (Cognito Access Control)
Quyền truy cập vào bảng điều khiển S3 + CloudFront được kiểm soát và xác thực nghiêm ngặt thông qua Amazon Cognito:
- **Xác thực (Authentication)**: Người dùng phải đăng nhập qua giao diện Cognito Hosted UI sử dụng luồng Authorization Code Flow bảo mật.
- **Quản lý phiên (Session Management)**: Các session token (ID, access, và refresh token) được trao đổi và lưu trữ dưới dạng secure cookies (chỉ HTTPS, cờ SameSite=Strict và Secure) với vòng đời ngắn.
- **S3 Origin Riêng tư**: Bucket S3 chứa các tài nguyên tĩnh được cấu hình hoàn toàn riêng tư. Mọi truy cập công cộng trực tiếp đều bị chặn bằng Origin Access Control (OAC), đảm bảo bảng điều khiển chỉ có thể truy cập qua CloudFront.
- **Ủy quyền Viewer-Request (Viewer-Request Authorization)**: Một hàm Lambda@Edge viewer-request sẽ chặn mọi yêu cầu đến CloudFront. Nó xác thực JWT token của Cognito trước khi trả về các file tĩnh hoặc dữ liệu JSON.
  *(Lưu ý kiến trúc: Lambda@Edge là bắt buộc ở đây do session token của Cognito sử dụng chữ ký bất đối xứng RS256, yêu cầu truy xuất public key động từ endpoint JWKS của Cognito. CloudFront Functions thông thường không hỗ trợ mật mã bất đối xứng hoặc gọi mạng ra ngoài. Tuy nhiên, như một tối ưu hóa trong tương lai, nếu cấu hình xác thực token đối xứng (HS256) hoặc phân phối public key qua CloudFront KeyValueStore, cổng auth có thể chuyển đổi sang CloudFront Functions để đạt chi phí bằng 1/6 so với Lambda@Edge và độ trễ dưới 1 mili-giây).*
- **Ủy quyền theo nhóm (Group-Based Authorization)**:
  - `finops-finance-readonly`: Thành viên có quyền xem xu hướng chi tiêu, tóm tắt bất thường, cảnh báo Finance, và liên kết kiểm toán. Người dùng Finance bị giới hạn nghiêm ngặt ở chế độ xem chỉ đọc và không bao giờ được thấy các rollback script thô, lệnh CLI, hoặc nút thực thi containment.
  - `finops-engineering-operator`: Thành viên có quyền xem chi tiết kỹ thuật bất thường, truy cập context role thực thi, và sử dụng các nút điều khiển Extend/Snooze hoặc Rollback/Restore đã phê duyệt.
  - `finops-cdo-admin`: Thành viên có toàn quyền quản trị để quản lý user pool, nhóm, chính sách truy cập bảng điều khiển, khả năng hiển thị dữ liệu giả lập, và các cấu hình vận hành.

### Backend API Endpoint
Để hỗ trợ các hành động tương tác trên dashboard (như hoàn tác thủ công, xác minh can thiệp hoặc truy xuất quyết định bất thường), đường dẫn API backend sử dụng một Application Load Balancer (ALB) nội bộ riêng tư hoặc HTTPS adapter tương đương fronting hàm AI Engine Lambda container chạy bên trong các subnets private.

ALB riêng tư này hiển thị các endpoint HTTPS `/v1/*` (bao gồm `/v1/detect`, `/v1/decide`, `/v1/verify`, `/v1/status/{id}`, `/v1/audit/{audit_id}/rollback`, và `/health`) sử dụng xác thực AWS SigV4. Dashboard frontend định tuyến các yêu cầu thông qua CloudFront, nơi xác thực các Cognito JWT session token tại ranh giới CloudFront/Lambda@Edge trước khi chuyển tiếp các yêu cầu một cách an toàn tới ALB nội bộ bên trong VPC.

Các Function URL Lambda công khai trực tiếp hoặc các đường dẫn Step Functions-to-AI-Lambda bỏ qua kiểm soát đều bị nghiêm cấm. Việc thực thi rollback độc lập và được xử lý trực tiếp bởi CDO backend worker chạy các cấu hình boto3 đã cache từ bảng DynamoDB `finops-rollback-cache`, tách biệt khỏi tính khả dụng của AI Engine.


---

## 2. Các chế độ xem trên bảng điều khiển (Dashboard views)

### 2.1 Xu hướng chi tiêu (Spend trend)
Chế độ xem Xu hướng chi tiêu hiển thị chi phí AWS hàng ngày trên các tài khoản trong một khoảng thời gian 90 ngày liên tục.
- **Trực quan hóa**: Biểu đồ miền hiển thị chi phí tích lũy hàng ngày tính bằng USD (unblended cost).
- **Đánh dấu bất thường (Anomaly Overlay)**: Các điểm mà AI Engine (do AIOps sở hữu) phát hiện bất thường được làm nổi bật bằng các dấu hiệu trực quan riêng biệt (ví dụ: các chỉ báo cảnh báo vào các ngày cụ thể).
- **Chỉ số so sánh**: Đường xu hướng baseline dạng nét đứt hiển thị chi tiêu lịch sử dự kiến so với nét liền đại diện cho chi tiêu thực tế, giúp các sai lệch chi phí hiển thị rõ ràng ngay lập tức.
- **Bộ lọc**: Các bộ lọc cho tài khoản AWS ID, tag tài nguyên, dịch vụ (ví dụ: EC2, EKS, RDS) và khoảng thời gian.

### 2.2 Chi tiết bất thường (Anomaly detail)
Khi người dùng nhấp vào một điểm đánh dấu bất thường hoặc chọn một sự kiện từ danh sách bất thường, chế độ xem Chi tiết bất thường sẽ được điền các bằng chứng quyết định:
- **Độ tin cậy trực quan**: Một thanh trượt phần trăm thể hiện độ tin cậy của mô hình, được dịch thành các xếp hạng ngôn ngữ tự nhiên (ví dụ: Cao, Trung bình, Thấp).
- **Độ tin cậy dữ liệu (Data Confidence)**: Thể hiện tính đầy đủ và chất lượng của dữ liệu đo lường hiệu năng đầu vào, được dịch thành các nhãn thân thiện với bộ phận Tài chính (Finance):
  - `HIGH`: "Thu thập đầy đủ (dữ liệu chi phí & hiệu năng đã xác thực)" - Bất thường được phát hiện bằng cách sử dụng các bản ghi thanh toán đã được chốt và dữ liệu hiệu suất tài nguyên.
  - `LOW`: "Dữ liệu đo lường bị chậm (dự phòng nguồn dữ liệu bị suy giảm)" - Dữ liệu telemetry bị trễ hoặc thiếu chỉ số hiệu suất, tự động chuyển sang chế độ dự phòng Cost Explorer hàng ngày hoặc CUR-only.
- **Mức độ nghiêm trọng (Severity)**: Được phân loại thành Nguy cấp (Critical - kích hoạt thông báo dry-run hoặc hành động containment ngay lập tức), Cảnh báo (Warning), hoặc Thấp (Low).
- **Cửa sổ bằng chứng (Evidence Window)**: Dấu thời gian bắt đầu và kết thúc của mô hình chi tiêu bất thường.
- **Văn bản giải thích (Explanation Text)**: Mô tả bằng ngôn ngữ tự nhiên được tạo bởi AI Engine (ví dụ: "Phát hiện tăng đột ngột 4× chi phí EC2 trên thực thể g5.4xlarge, điển hình cho các cụm huấn luyện máy học không được quản lý").
- **Chi phí chênh lệch (Cost Delta)**: Lượng lãng phí tài chính ước tính tính bằng USD/ngày.

### 2.3 Các tài khoản/dịch vụ/squad bị ảnh hưởng nhiều nhất (Top impacted accounts/services/squads)
Chế độ xem dạng bảng giúp tổng hợp chi tiêu bất thường và xếp hạng các nguồn lãng phí để hỗ trợ các quyết định định tuyến:
- **Bảng xếp hạng Squad (Squad Leaderboard)**: Xếp hạng các squad dựa trên tổng chi phí chênh lệch từ các bất thường đang hoạt động (ví dụ: `squad-prediction-models` là nhóm chi tiêu nhiều nhất).
- **Phân rã theo dịch vụ**: Hiển thị dịch vụ AWS nào chịu trách nhiệm cho các bất thường (ví dụ: 85% EC2, 15% NAT Gateway).
- **Trạng thái tag chủ sở hữu (Owner Tag Status)**: Làm nổi bật các tài nguyên bị thiếu hoặc sai tag `owner`/`squad`, định tuyến chúng theo mặc định về kênh hạ tầng trung tâm của đội CDO.

### 2.4 Trạng thái containment (Containment status)
Một bảng kiểm toán tương tác liệt kê tất cả các hành động chính sách tự động và được đề xuất:
- **Hành động containment đang hoạt động**: Bảng hiển thị ID tài nguyên, tài khoản, squad sở hữu, loại hành động (ví dụ: Tagging, Sandbox Shutdown, Quota Cap) và thời gian thực thi.
- **Chế độ thực thi (Execution Mode)**: Gắn nhãn rõ ràng cho các hành động là `dry-run` (giả lập containment hoặc chỉ đề xuất) hoặc `apply` (áp dụng tự động chính sách trên môi trường non-production).
- **Đường liên kết bản ghi kiểm toán**: Một đường liên kết trực tiếp, có thể nhấp để xem bản ghi kiểm toán không thể sửa đổi được lưu trữ dưới dạng đối tượng S3 JSON. Mỗi liên kết tham chiếu đến Correlation ID và Idempotency Key duy nhất của lượt chạy.
- **Các trường trạng thái & thông tin chi tiết sự cố dựa trên hợp đồng (Contract-Backed Status & Incident Detail Fields)**: Giao diện người dùng hiển thị các tham số chính được truy vấn trực tiếp từ kho lưu trữ có thẩm quyền S3 (với việc cache trên DynamoDB để hiển thị nhanh chóng trên dashboard), đại diện cho ngữ nghĩa hợp đồng API v1.3:
  - `audit_id`: Mã định danh duy nhất cho phiên kiểm toán sự cố (ví dụ: `ANM-YYYY-MMDD[A-Z]`).
  - `status`: Trạng thái sự cố (ví dụ: `PENDING_APPROVAL`, `IN_PROGRESS`, `SUCCESS`, `ROLLED_BACK`, `ESCALATED`).
  - `containment_locked`: Cờ Boolean cho biết liệu việc tự động can thiệp có bị khóa hay không (chỉ cho phép `dry_run_mode: true` only) do vi phạm ngân sách lỗi.
  - `error_budget_remaining_pct`: Tỷ lệ ngân sách lỗi còn lại của tenant (0% đến 100%).
  - **Nhật ký hành động (Actions Log)**: Lịch sử từng bước bao gồm dấu thời gian, loại hành động, trạng thái và tác nhân thực hiện (ví dụ: `tag-for-review`, `auto-shutdown`, `quota-cap`).
- **Chỉ báo Khóa ngân sách lỗi (Error Budget Lock - LOCKED_MODE)**: Một biểu ngữ nổi bật trên bảng điều khiển hiển thị `X-Containment-Status: LOCKED` nếu tỷ lệ hoàn tác (rollback) vượt quá ngưỡng ngân sách lỗi. Biểu ngữ hiển thị lý do khóa (`error_budget_exceeded_threshold`), dấu thời gian khóa và vô hiệu hóa mọi nút chuyển đổi "Apply", bắt buộc mọi quyết định chạy ở chế độ dry-run. Việc khóa được phân tầng theo môi trường:
  - **Môi trường Sản xuất (Prod)**: Bị khóa nếu tỷ lệ rollback > 1%.
  - **Môi trường Staging**: Bị khóa nếu tỷ lệ rollback > 10%.
  - **Môi trường Phát triển/Sandbox (Dev)**: Tính năng khóa bị vô hiệu hóa (không bao giờ bị khóa, ngưỡng ngân sách lỗi không áp dụng).
- **Quy trình xác thực (Verification Flow)**: Người vận hành được phân quyền có thể kích hoạt xác thực việc khắc phục bằng cách gửi báo cáo thực thi và dữ liệu telemetry sau can thiệp (qua lệnh gọi API `/v1/verify`). Giao diện người dùng hiển thị giá trị `next_action` được trả về (như `DONE`, `RETRY`, `ROLLBACK`, hoặc `ESCALATE`).
- **Hành vi Khôi phục/Hoàn tác (Rollback/Restore Behavior)**: Cho phép các kỹ sư kích hoạt khôi phục thủ công (đại diện cho ngữ nghĩa `/v1/audit/{audit_id}/rollback`), được hiển thị dưới dạng nút **Rollback**.
  - *Tham số request*: `reason` (lý do rollback), `rolled_back_by` (email người thực hiện), `rollback_executed_at` (dấu thời gian thực thi hoàn tác), `rollback_status` (trạng thái khôi phục), và tùy chọn `boto3_result` (thông tin chi tiết về thực thi khôi phục).
  - *Phản hồi/Trạng thái giao diện mong muốn*: Xác nhận khởi tạo rollback, trả về `audit_recorded = true` (thay vì `rollback_initiated`), cập nhật tỷ lệ hao hụt ngân sách lỗi (`new_error_budget_burned_pct`) và chuyển trạng thái sự cố sang `ROLLED_BACK`.
  - *Logic thực thi Rollback (Rollback Execution Logic)*: Hành động rollback được xử lý trực tiếp bởi CDO backend. Khi được kích hoạt, CDO backend đọc cấu hình `rollback_payload.boto3_equivalent` đã được lưu trữ cache trong kho lưu trữ có thẩm quyền S3, thực thi các hành động rollback trực tiếp thông qua các API tiêu chuẩn của AWS SDK (Boto3/CLI) (đảm bảo việc khôi phục hoạt động bình thường ngay cả khi AI Engine ngoại tuyến), sau đó thông báo cho endpoint kiểm toán của AI Engine về trạng thái và thông tin chi tiết của quá trình thực thi.
- **Giới hạn kiểm soát truy cập (Access Control Restriction)**: Các lệnh khôi phục thô và kế hoạch thực thi bị giới hạn nghiêm ngặt, chỉ hiển thị và có khả năng thực thi bởi các kỹ sư CDO/Kỹ thuật được phân quyền dưới các IAM policy riêng biệt và nhóm người dùng Cognito. Người dùng Tài chính (Finance) chỉ tương tác với các trạng thái trực quan cấp cao và không bao giờ nhìn thấy hoặc thực thi các CLI command.

---

## 3. Định tuyến cảnh báo (Alert routing)

Hàm Lambda định tuyến cảnh báo (Alert Routing Lambda) xử lý đầu ra hợp đồng quyết định của AI và định tuyến các thông báo một cách linh hoạt dựa trên mức độ nghiêm trọng của bất thường, squad sở hữu và môi trường mục tiêu.

### 3.1 Cảnh báo Finance (Finance alerts)
Các bất thường mức độ nghiêm trọng cao hoặc các sự kiện vượt quá ngưỡng ngân sách cụ thể (ví dụ: chi phí chênh lệch >100 USD/ngày) được định tuyến đến kênh thông báo của Finance.
- **Kênh phân phối**: Amazon SES (Email) or Amazon SNS (SMS/Pager).
- **Trọng tâm nội dung**: Tác động tài chính (USD delta), độ tin cậy dữ liệu (`HIGH`/`LOW` với các nhãn ngôn ngữ tự nhiên), trạng thái hành động containment hiện tại, đường liên kết kiểm toán S3/CloudFront và siêu dữ liệu cho biết khả năng khôi phục/gia hạn có tồn tại cho bất thường đó hay không.
- **Ràng buộc bảo mật (Security Constraint)**: Không bao gồm bất kỳ nút hành động trực tiếp hoặc câu lệnh CLI nào trong các thông báo cảnh báo công khai của Finance.
- **Tần suất**: Các thông báo batch hàng ngày, với khả năng leo thang ngay lập tức đối với các đột biến chi phí nguy cấp.

### 3.2 Cảnh báo Kỹ thuật (Engineering alerts)
Tất cả các bất thường được phát hiện được định tuyến trực tiếp đến các squad chịu trách nhiệm về tài nguyên mục tiêu.
- **Kênh phân phối**: Slack Webhook (Các kênh squad chuyên dụng) hoặc Jira API (tự động tạo ticket). Các URL webhook của Squad được truy xuất động bằng cách sử dụng đối tượng cấu hình `slack_routing` được trả về trong phản hồi `/v1/decide` (định nghĩa `channel_name` và `webhook_url_pointer`).
- **Trọng tâm nội dung**: ID tài nguyên kỹ thuật (ARN), loại dịch vụ, môi trường (Dev/Sandbox/Prod), trạng thái tuân thủ tag, trạng thái độ tin cậy dữ liệu (`HIGH`/`LOW`), và đường dẫn rollback đề xuất.
- **Kiểm soát hành động (Action Control)**: Include các liên kết hành động Xác thực và Hoàn tác ngắn hạn, được xác thực (thực thi đối với lớp API đại diện cho ngữ nghĩa `/v1/verify` và `/v1/audit/{audit_id}/rollback`) khi chính sách và cấu hình môi trường cho phép.
- **Tần suất & Gom nhóm (Frequency & Aggregation)**: Để ngăn ngừa tình trạng quá tải thông báo (alert fatigue) và tin nhắn rác trên Slack, Lambda Cảnh báo sẽ tổng hợp (gom nhóm) các cảnh báo theo `Squad_ID` và gửi chúng dưới dạng một tin nhắn Digest (Tóm tắt) hàng ngày duy nhất (thay vì gửi tin nhắn rác gần như thời gian thực cho từng bất thường riêng lẻ, chẳng hạn như 50 pod bị lỗi đồng thời). Bản tóm tắt liệt kê các bất thường nghiêm trọng nhất cần chú ý.

*Ghi chú về dữ liệu telemetry*: Dữ liệu đo lường được xử lý để phát hiện bất thường là dạng lai (hybrid), bao gồm các tệp xuất S3 CUR, dữ liệu API Cost Explorer và các chỉ số hiệu năng từ CloudWatch (`resource_utilization_metrics` như CPU, memory, network, disk, database connections, và GPU metrics). Nếu các chỉ số CloudWatch không khả dụng, hệ thống tự động chuyển sang chế độ CUR-only, thiết lập `data_confidence = LOW` và bắt buộc thực hiện các hành động containment ở chế độ dry-run/alert-only.

### 3.3 Xử lý lỗi API hợp đồng (API contract error handling)
Khi người vận hành kích hoạt các nút điều khiển hành động, hệ thống bảng điều khiển và cảnh báo sẽ xử lý các lỗi hợp đồng sau:
- **`ERR_INVALID_SCHEMA`**: Body không tuân thủ schema hoặc thiếu các trường bắt buộc. Giao diện cảnh báo cho người vận hành và ghi nhật ký lỗi mà không thử lại.
- **`ERR_IDEMPOTENCY_MISMATCH`**: Yêu cầu sử dụng trùng `X-Idempotency-Key` nhưng body yêu cầu khác nhau.
- **`ERR_REPLAY_DETECTED`**: Độ lệch thời gian của yêu cầu vượt quá 300 giây. Client thực hiện đồng bộ hóa thời gian NTP và thử lại.
- **`ERR_CROSS_TENANT_DENIED`**: Mã định danh tenant trong `X-Tenant-Id` không khớp với ngữ cảnh tài nguyên. Truy cập bị chặn ngay lập tức và tạo cảnh báo bảo mật.
- **`ERR_ANOMALY_NOT_FOUND`**: Không tìm thấy `anomaly_id` tương ứng trong cơ sở dữ liệu.
- **`ERR_DUP_IDEMPOTENCY`**: Khóa yêu cầu đang được xử lý (`IN_PROGRESS`). Nền tảng CDO thực hiện thăm dò `GET /v1/status/{id}` cho trạng thái tự chữa lành cho đến khi hoàn thành.
- **`ERR_CONTAINMENT_NOT_SUPPORTED`**: Loại bất thường không hỗ trợ tự động containment. Giao diện hướng dẫn người dùng liên hệ đội SRE.
- **`ERR_RATE_LIMITED`**: Lượt gọi vượt quá 100 requests/phút. Client thực hiện exponential backoff.
- **`ERR_LLM_TIMEOUT` / `ERR_SERVICE_DOWN`**: AI Engine không khả dụng hoặc bị timeout. Nền tảng CDO kích hoạt hệ thống luật fallback tĩnh nội bộ.

### 3.4 Khả năng quan sát callback (Callback observability)
Đối với các tích hợp sử dụng callback để thông báo cho CDO về trạng thái bất thường:
- **Ghi nhật ký đo lường (Telemetry Logging)**: Việc truyền tải callback được ghi nhật ký dưới dạng dữ liệu đo lường vận hành của nền tảng.
- **Cô lập đồng bộ (Synchronous Isolation)**: Thất bại trong việc gửi callback (ngay cả sau khi đã thử lại hết số lần cấu hình) không làm lỗi hoặc mất hiệu lực kết quả phát hiện đồng bộ chính.

### 3.5 Payload cảnh báo mẫu (Example alert payload)
Alert Routing Lambda sử dụng một hợp đồng JSON có cấu trúc. Schema dưới đây đại diện cho một payload cảnh báo điển hình được gửi đến các kênh thông báo:

```json
{
  "alert_id": "alert-uuid-7777-8888-9999",
  "anomaly_id": "ANM-2026-0623A",
  "anomaly_type": "runaway_usage",
  "severity": "HIGH",
  "confidence_score": 0.94,
  "data_confidence": "HIGH",
  "resource_id": "arn:aws:ec2:ap-southeast-1:123456789012:instance/i-0abcd1234efgh5678",
  "environment": "sandbox",
  "responsible_team": "squad-prediction-models",
  "unblended_cost_24h_usd": 427.50,
  "cost_ratio_to_7d_avg": 18.2,
  "ai_model_used": "amazon.nova-pro-v1:0",
  "alert_routing": {
    "finance": true,
    "engineering": true
  },
  "slack_routing": {
    "channel_name": "#squad-prediction-models",
    "webhook_url_pointer": "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:slack/squad-prediction-models"
  },
  "audit_id": "8f3b610c-18a4-4e2b-9801-bde901844b20",
  "correlation_id": "corr-uuid-4444-5555-6666",
  "timestamp": "2026-06-23T07:30:00Z",
  "containment": {
    "proposed_action": "stop_instance",
    "execution_mode": "dry-run",
    "idempotency_key": "tenant-uuid-1111-2222-3333:2026-06-22:daily_batch",
    "audit_record_uri": "s3://company-cdo-123456789012-telemetry/audit/year=2026/month=06/corr-uuid-4444-5555-6666.json"
  }
}
```

*Ghi chú phân tách dữ liệu (Data Separation Note)*: Các trường kỹ thuật và hành chính như `audit_trail_context.pre_action_state`, `audit_trail_context.post_action_state`, và `audit_trail_context.rollback_script_encapsulated` được đối xử nghiêm ngặt dưới dạng siêu dữ liệu kiểm toán và quản trị được lưu trữ bảo mật trong S3/Object Lock và S3 Audit Trail. Các chi tiết này hoàn toàn bị loại bỏ khỏi payload cảnh báo công khai và các kênh Finance để bảo vệ tính dễ đọc và thực thi ranh giới bảo mật.

---

## 4. Khả năng tiếp cận và tính dễ đọc (Accessibility and readability)

Để đảm bảo nền tảng CDO hoàn toàn dễ đọc với bộ phận Finance và không yêu cầu kiến thức SQL, dashboard S3 + CloudFront áp dụng các quy tắc trực quan hóa sau:
- **Dịch sang ngôn ngữ tự nhiên**: Các chỉ số mô hình được dịch thành các tác động tài chính trực quan. Ví dụ: điểm độ tin cậy mô hình `0.89` được hiển thị dưới dạng "Độ tin cậy cao (89%)".
- **Tiêu chuẩn tiền tệ USD**: Tất cả chi phí được chuẩn hóa và hiển thị bằng USD (đô la Mỹ).
- **Bộ lọc trực quan**: Người dùng tương tác với dữ liệu qua các hộp chọn dropdown, danh sách checkbox và bộ chọn ngày lịch. Các trường nhập mã SQL, schema cơ sở dữ liệu thô và các trình xây dựng truy vấn kiểu terminal hoàn toàn bị loại bỏ khỏi giao diện người dùng.
- **Đơn giản hóa kiểm toán**: Trạng thái cấu hình trước/sau được biểu diễn dưới dạng so khớp trực quan (visual diff với các tag màu được thêm/bớt hoặc thay đổi trạng thái) thay vì hiển thị các đối tượng JSON thô cho người dùng cuối.

---

## 5. Câu hỏi mở (Open questions)

- [ ] **Giới hạn tỷ lệ Slack Webhook**: Số lượng tin nhắn Slack tối đa hàng ngày được phép gửi cho mỗi kênh squad là bao nhiêu để ngăn ngừa tình trạng quá tải thông báo (alert fatigue)?
- [ ] **Giao diện người dùng phê duyệt manual**: Đối với các hành động containment ở chế độ apply trên môi trường non-production yêu cầu phê duyệt thủ công, các nút phê duyệt nên được host trên chính dashboard hay nhúng trực tiếp trong tin nhắn tương tác của Slack?
- [ ] **Lộ trình tích hợp QuickSight BI**: Tại thời điểm nào trong việc mở rộng quy mô nền tảng (ví dụ: >10 người dùng Finance hoặc >100 tài khoản AWS), công ty nên chuyển đổi từ dashboard tĩnh S3 + CloudFront sang Amazon QuickSight Enterprise?

---

## Tài liệu liên quan (Related documents)

- [`01_requirements_analysis_vi.md`](01_requirements_analysis_vi.md) - Yêu cầu nghiệp vụ doanh nghiệp, các NFRs về tài chính và phân chia trách nhiệm CDO/AIOps.
- [`02_infra_design_vi.md`](02_infra_design_vi.md) - Kiến trúc vĩ mô hiển thị luồng thu thập dữ liệu, Lambda container-hosted AI Engine, hồ lưu trữ dữ liệu và lớp dashboard S3 + CloudFront.
