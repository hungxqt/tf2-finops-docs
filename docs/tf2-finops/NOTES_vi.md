# Tài liệu Ghi chú - Task Force 2 · FinOps Watch CDO

Tài liệu này đóng vai trò hướng dẫn vận hành cho đội ngũ kỹ thuật và CDO khi chuyển đổi tài liệu thiết kế sang giai đoạn triển khai thực tế.

## 1. Chiến lược Giữ chỗ: "Evidence needed" / "Cần bằng chứng"

Trong toàn bộ tài liệu CDO, bạn sẽ tìm thấy các phần giữ chỗ được đánh dấu như sau:
- **Tiếng Anh**: `Evidence needed: <mô tả chỉ số>`
- **Tiếng Việt**: `Cần bằng chứng: <mô tả chỉ số>`

### Mục đích

Các phần giữ chỗ này thể hiện các chỉ số vận hành, dữ liệu đo lường (telemetry), số liệu chi phí AWS và kết quả xác thực thực tế **không thể giả lập hoặc xác định chính xác trong giai đoạn thiết kế và kiến trúc**. Chúng đại diện cho bằng chứng thực nghiệm cần thiết để đáp ứng các yêu cầu phi chức năng (NFR), Mục tiêu Mức độ Dịch vụ (SLO) và mô hình chi phí của nền tảng.

Việc sử dụng các phần giữ chỗ này giúp tránh việc đưa các số liệu giả lập, chưa được xác minh vào tài liệu chính thức như thể là dữ liệu telemetry sản xuất, đảm bảo tính tuân thủ và minh bạch cho các nhật ký kiểm toán tài chính và kỹ thuật.

### Phạm vi của Telemetry

Tuân thủ theo các hợp đồng telemetry và API đã ký:
1. **Khả năng quan sát của CDO Platform**: Các phép đo thực tế phải ghi nhận cho các adapter do CDO sở hữu (thời gian chạy Lambda, độ trễ hàng đợi SQS/DLQ, khối lượng định tuyến qua Private ALB, và kích thước truy vấn Athena) và các thông số vận hành của nền tảng host.
2. **Thực thi Workload AI**: CDO đóng vai trò là môi trường host cho container AI Engine do AIOps cung cấp. Thời lượng thực thi, dung lượng bộ nhớ tiêu thụ và mô hình concurrency của engine được host phải được theo dõi và bóc tách riêng khỏi chi phí nền tảng CDO.
3. **Phạm vi Đo lường Hybrid Telemetry (Hybrid Telemetry Scope)**: Bên cạnh dữ liệu chi phí (CUR và fallback qua API Cost Explorer), luồng phát hiện bất thường sử dụng thêm các chỉ số hiệu suất hạ tầng CloudWatch. Cụ thể, CDO sẽ gửi một mảng `cpu_utilization_hourly` chứa các chỉ số hiệu suất CPU theo giờ. Nếu thiếu dữ liệu đo lường hiệu năng CloudWatch, hệ thống tự động chuyển sang chế độ dự phòng CUR-only, thiết lập `data_confidence = LOW` và giới hạn các biện pháp can thiệp ở chế độ dry-run/cảnh báo.
4. **Thu thập dữ liệu hàng ngày & Dự phòng Cost Explorer**: Trong điều kiện vận hành bình thường, CDO platform thực thi luồng công việc **phát hiện bất thường hàng ngày ưu tiên CUR (CUR-first)**. Nếu quá trình truyền dữ liệu S3 CUR bị trễ (được gắn cờ `telemetry_delay_event = true` trong hợp đồng API), nền tảng tự động chuyển sang cơ chế dự phòng bằng cách truy vấn trực tiếp API AWS Cost Explorer để lấy các chỉ số chi phí. Trong kịch bản dự phòng này, AI Engine sẽ phản hồi với độ tin cậy `data_confidence = LOW` và CDO platform sẽ ghi đè chế độ containment sang chế độ **dry-run/chỉ cảnh báo (dry-run/alert-only containment mode)** nhằm tránh các hành động tự động hóa sai lầm dựa trên dữ liệu trễ.

### Hướng dẫn Cập nhật Sau khi Triển khai

Khi hạ tầng được triển khai thành công trên các tài khoản AWS staging/production và chu kỳ chạy hàng loạt hàng ngày được kích hoạt, đội ngũ kỹ thuật phải:

1. **Thu thập Telemetry**: Sử dụng AWS Cost Explorer (lọc theo tag `Project=TF2-FinOps-CDO06`), CloudWatch Metrics, AWS X-Ray traces, và nhật ký chạy DynamoDB để thu thập các giá trị thực tế.
2. **Thay thế phần Giữ chỗ**: Định vị từng phần giữ chỗ trong các tài liệu và thay thế chúng bằng các số liệu thu thập được, liên kết đến các đường dẫn kiểm toán S3, hoặc ảnh chụp màn hình dashboard CloudWatch.
3. **Các Tài liệu Chính bị Ảnh hưởng**:
   - [05_cost_analysis.md](05_cost_analysis.md) / [05_cost_analysis_vi.md](05_cost_analysis_vi.md): Cập nhật các bảng dự báo và chi phí thực tế ở Mục 1, Mục 2, Mục 5, và Mục 5.3 (Chi phí trên mỗi Quyết định Đúng).
   - [07_test_eval_report.md](07_test_eval_report.md) / [07_test_eval_report_vi.md](07_test_eval_report_vi.md): Cập nhật Mục 2 (Bảng bằng chứng SLO với tỷ lệ thành công/độ tươi của dữ liệu đo được) và Mục 8.2 (các khoảng trống kiểm thử được thừa nhận).

## 2. Quy tắc Xác minh Tính Đồng bộ

Khi cập nhật các phần giữ chỗ này:
- Duy trì tính đồng bộ 100% giữa các tệp tiếng Anh chính và các bản dịch tiếng Việt tương ứng (`_vi.md`).
- Chạy tập lệnh xác minh cục bộ (`verify_docs.py`) để xác nhận số lượng tiêu đề (headings), cấu trúc khối mã và vị trí liên kết vẫn hoàn toàn trùng khớp.
