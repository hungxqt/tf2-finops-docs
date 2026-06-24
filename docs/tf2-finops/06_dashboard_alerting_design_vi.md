# Thiết kế Bảng điều khiển & Cảnh báo (Dashboard & Alerting Design) - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Refined (W12 T4 Pack #2)
-->

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
Một bảng điều khiển web nội bộ nhẹ được lưu trữ dưới dạng tài sản tĩnh trong Amazon S3 và phân phối qua Amazon CloudFront. Bảng điều khiển đọc các bản tóm tắt thân thiện với tài chính được tính toán trước từ các đối tượng S3 JSON hoặc bản ghi DynamoDB được tạo ra bởi luồng công việc thu thập dữ liệu theo lịch trình của Step Functions. Athena vẫn hoạt động phía sau để tạo các bản tóm tắt được tinh lọc; người dùng Tài chính không bao giờ phải viết mã SQL.

QuickSight được giữ lại như một tùy chọn BI trong tương lai cho các nhóm Tài chính lớn hơn hoặc báo cáo ban điều hành, nhưng nó không phải là bảng điều khiển MVP mặc định vì capstone ưu tiên chi phí định kỳ thấp và không có phí seat cho mỗi reader BI.

---

## 2. Các chế độ xem trên bảng điều khiển (Dashboard views)

### 2.1 Xu hướng chi tiêu (Spend trend)
Chế độ xem Xu hướng chi tiêu hiển thị chi phí AWS hàng ngày trên các tài khoản trong một khoảng thời gian 90 ngày liên tục.
- **Trực quan hóa**: Biểu đồ miền hiển thị chi phí tích lũy hàng ngày tính bằng USD (unblended cost).
- **Đánh dấu bất thường (Anomaly Overlay)**: Các điểm mà AI Engine (do AIOps sở hữu) phát hiện bất thường được làm nổi bật bằng các dấu hiệu trực quan riêng biệt (ví dụ: các chỉ báo cảnh báo vào các ngày cụ thể).
- **Chỉ số so sánh**: Đường xu hướng baseline dạng nét đứt hiển thị chi tiêu lịch sử dự kiến so với nét liền đại diện cho chi tiêu thực tế, giúp các sai lệch chi phí hiển thị rõ ràng ngay lập tức.
- **Bộ lọc**: Các bộ lọc cho tài khoản AWS ID, tag tài nguyên, dịch vụ (ví dụ: EC2, ECS, RDS) và khoảng thời gian.

### 2.2 Chi tiết bất thường (Anomaly detail)
Khi người dùng nhấp vào một điểm đánh dấu bất thường hoặc chọn một sự kiện từ danh sách bất thường, chế độ xem Chi tiết bất thường sẽ được điền các bằng chứng quyết định:
- **Độ tin cậy trực quan**: Một thanh trượt phần trăm thể hiện độ tin cậy của mô hình, được dịch thành các xếp hạng ngôn ngữ tự nhiên (ví dụ: Cao, Trung bình, Thấp).
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
- **Giao diện khôi phục (Rollback Interface)**: Một nút cho phép quản trị viên xem đường dẫn rollback được xác định trước (ví dụ: khôi phục trạng thái tag ban đầu hoặc khởi động lại một instance non-production).

---

## 3. Định tuyến cảnh báo (Alert routing)

Hàm Lambda định tuyến cảnh báo (Alert Routing Lambda) xử lý đầu ra hợp đồng quyết định của AI và định tuyến các thông báo một cách linh hoạt dựa trên mức độ nghiêm trọng của bất thường, squad sở hữu và môi trường mục tiêu.

### 3.1 Cảnh báo Finance (Finance alerts)
Các bất thường mức độ nghiêm trọng cao hoặc các sự kiện vượt quá ngưỡng ngân sách cụ thể (ví dụ: chi phí chênh lệch >100 USD/ngày) được định tuyến đến kênh thông báo của Finance.
- **Kênh phân phối**: Amazon SES (Email) hoặc Amazon SNS (SMS/Pager).
- **Trọng tâm nội dung**: Tác động tài chính (USD delta), quyền sở hữu tài khoản, độ tin cậy của mô hình AI, hành động containment đề xuất và liên kết dashboard S3 + CloudFront.
- **Tần suất**: Các thông báo batch hàng ngày, với khả năng leo thang ngay lập tức đối với các đột biến chi phí nguy cấp.

### 3.2 Cảnh báo Kỹ thuật (Engineering alerts)
Tất cả các bất thường được phát hiện được định tuyến trực tiếp đến các squad chịu trách nhiệm về tài nguyên mục tiêu.
- **Kênh phân phối**: Slack Webhook (Các kênh squad chuyên dụng) hoặc Jira API (tự động tạo ticket).
- **Trọng tâm nội dung**: ID tài nguyên kỹ thuật (ARN), loại dịch vụ, môi trường (Dev/Sandbox/Prod), trạng thái tuân thủ tag, đường dẫn rollback được đề xuất và một liên kết để phê duyệt hoặc tạm ẩn (snooze) hành động containment.
- **Tần suất**: Gần như thời gian thực (trong vòng 30 phút sau khi pipeline hoàn thành).

*Ghi chú về dữ liệu telemetry*: Dữ liệu telemetry truyền cho AI Engine phục vụ phát hiện bất thường là dữ liệu chi phí CUR-only và loại bỏ hoàn toàn các metric hiệu năng (CPU, memory, connections). Các metric CloudWatch chỉ phục vụ cho lớp giám sát vận hành của CDO platform và hiển thị dashboard.

### 3.3 Payload cảnh báo mẫu (Example alert payload)
Alert Routing Lambda sử dụng một hợp đồng JSON có cấu trúc. Schema dưới đây đại diện cho một payload cảnh báo điển hình được gửi đến các kênh thông báo:

```json
{
  "alert_id": "alert-uuid-7777-8888-9999",
  "anomaly_id": "anom-9988-7766",
  "correlation_id": "corr-uuid-4444-5555-6666",
  "timestamp": "2026-06-23T07:30:00Z",
  "routing_target": "squad-prediction-models",
  "notification_channel": "Slack",
  "severity": "Critical",
  "financials": {
    "currency": "USD",
    "actual_daily_spend": 412.50,
    "expected_daily_spend": 12.50,
    "daily_delta": 400.00
  },
  "ai_evidence": {
    "model_version": "v1.2.0",
    "confidence_score": 0.89,
    "explanation": "Unmanaged GPU instance cluster running without active container tasks in sandbox environment."
  },
  "resource_details": {
    "arn": "arn:aws:ec2:ap-southeast-1:123456789012:instance/i-0abcdef123456",
    "environment": "sandbox",
    "owner_tag": "squad-prediction-models"
  },
  "containment": {
    "proposed_action": "stop_instance",
    "execution_mode": "dry-run",
    "idempotency_key": "tenant_id:2026-06-22",
    "audit_record_uri": "s3://cdo-audit-trail-bucket/audit/year=2026/month=06/corr-uuid-4444-5555-6666.json"
  }
}
```

---

## 4. Khả năng tiếp cận và tính dễ đọc (Accessibility and readability)

Để đảm bảo nền tảng CDO hoàn toàn dễ đọc với bộ phận Finance và không yêu cầu kiến thức SQL, dashboard S3 + CloudFront áp dụng các quy tắc trực quan hóa sau:
- **Dịch sang ngôn ngữ tự nhiên**: Các chỉ số mô hình được dịch thành các tác động tài chính trực quan. Ví dụ: điểm độ tin cậy mô hình `0.89` được hiển thị dưới dạng "Độ tin cậy cao (89%)".
- **Tiêu chuẩn tiền tệ USD**: Tất cả chi phí được chuẩn hóa và hiển thị bằng USD (đô la Mỹ).
- **Bộ lọc trực quan**: Người dùng tương tác với dữ liệu qua các hộp chọn dropdown, danh sách checkbox và bộ chọn ngày lịch. Các trường nhập mã SQL, schema cơ sở dữ liệu thô và các trình xây dựng truy vấn kiểu terminal hoàn toàn bị loại bỏ khỏi giao diện người dùng.
- **Đơn giản hóa kiểm toán**: Trạng thái cấu hình trước/sau được biểu diễn dưới dạng so khớp trực quan (visual diff với các tag màu được thêm/bớt hoặc thay đổi trạng thái) thay vì hiển thị các đối tượng JSON thô cho người dùng cuối.

---

## 5. Câu hỏi mở (Open questions)

- [ ] **Tích hợp Cognito vs. Basic Auth**: Việc kiểm soát truy cập vào trang web tĩnh S3 + CloudFront nên được quản lý qua tích hợp AWS Cognito OIDC hay cơ chế Basic Auth gọn nhẹ sử dụng CloudFront Lambda@Edge?
- [ ] **Giới hạn tỷ lệ Slack Webhook**: Số lượng tin nhắn Slack tối đa hàng ngày được phép gửi cho mỗi kênh squad là bao nhiêu để ngăn ngừa tình trạng quá tải thông báo (alert fatigue)?
- [ ] **Giao diện người dùng phê duyệt manual**: Đối với các hành động containment ở chế độ apply trên môi trường non-production yêu cầu phê duyệt thủ công, các nút phê duyệt nên được host trên chính dashboard hay nhúng trực tiếp trong tin nhắn tương tác của Slack?
- [ ] **Lộ trình tích hợp QuickSight BI**: Tại thời điểm nào trong việc mở rộng quy mô nền tảng (ví dụ: >10 người dùng Finance hoặc >100 tài khoản AWS), công ty nên chuyển đổi từ dashboard tĩnh S3 + CloudFront sang Amazon QuickSight Enterprise?

---

## Tài liệu liên quan (Related documents)

- [`01_requirements_analysis_vi.md`](01_requirements_analysis_vi.md) - Yêu cầu nghiệp vụ doanh nghiệp, các NFRs về tài chính và phân chia trách nhiệm CDO/AIOps.
- [`02_infra_design_vi.md`](02_infra_design_vi.md) - Kiến trúc vĩ mô hiển thị luồng thu thập dữ liệu, ECS AI Engine hosting, hồ lưu trữ dữ liệu và lớp dashboard S3 + CloudFront.
