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
1. **Khả năng quan sát của CDO Platform**: Các phép đo thực tế phải ghi nhận cho các adapter do CDO sở hữu (thời gian chạy Lambda, độ trễ hàng đợi SQS/DLQ, khối lượng gọi hàm Lambda trực tiếp, và kích thước truy vấn Athena) và các thông số vận hành của nền tảng host.
2. **Thực thi Workload AI**: CDO đóng vai trò là môi trường host cho container AI Engine do AIOps cung cấp. Thời lượng thực thi, dung lượng bộ nhớ tiêu thụ và mô hình concurrency của engine được host phải được theo dõi và bóc tách riêng khỏi chi phí nền tảng CDO.
3. **Phạm vi Đo lường Hybrid Telemetry**: Bên cạnh dữ liệu chi phí (CUR và Cost Explorer API), luồng phát hiện bất thường sử dụng thêm các chỉ số hiệu suất hạ tầng CloudWatch (`resource_utilization_metrics` như CPU, bộ nhớ, và hiệu suất sử dụng cơ sở dữ liệu). Nếu thiếu dữ liệu đo lường CloudWatch, nền tảng sẽ tự động kích hoạt chế độ dự phòng CUR-only, làm giảm một nửa độ tin cậy phát hiện (`confidence *= 0.5`) và giới hạn các biện pháp can thiệp ở chế độ dry-run/cảnh báo thuần túy.

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
