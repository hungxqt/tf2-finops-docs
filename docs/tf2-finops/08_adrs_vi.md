# Quyết định Thiết kế Kiến trúc (Architecture Decision Records) - FinOps Watch CDO · Task Force 2

<!-- Doc owner: CDO Team
     Status: Ongoing log W11-W12
     Format: 1 ADR per major decision. Append-only - do not delete old ADRs. -->

> **ADR là gì (What is an ADR)**: Nhật ký ghi lại mỗi quyết định kiến trúc quan trọng và lý do tại sao chọn phương án đó (thay vì các phương án khác). Mục đích là để đảm bảo các nhà phát triển trong tương lai hiểu rõ tại sao một hướng đi cụ thể lại được chọn thay vì các phương án thay thế.
>
> **Khi nào viết ADR (When to write an ADR)**:
> - Quyết định có sự đánh đổi thực tế (real trade-offs) (chọn Phương án X có chi phí, chọn Phương án Y có lợi ích).
> - Quyết định có chi phí đảo ngược cao (high reversal cost) (ví dụ: thay đổi mục tiêu tính toán nghĩa là phải xây dựng lại hạ tầng).
> - Quyết định có thể bị chất vấn trong các buổi đánh giá hoặc bảo vệ kiến trúc.
>
> **Không viết ADR cho (Do not write an ADR for)**: Các quyết định nhỏ không có sự đánh đổi lớn (tên tài nguyên, quy ước lập trình nhỏ, v.v.).
>
> **Khi một ADR cũ không còn áp dụng (When an old ADR is no longer applicable)**: Đánh dấu trạng thái là `Status: Superseded by ADR-NNN` (Được thay thế bởi ADR-NNN). Không xóa ADR cũ. Nhật ký này là append-only (chỉ ghi thêm).

---

## ADR-001 - Chu kỳ 24 giờ thay vì 12 giờ/48 giờ (24h cadence over 12h/48h)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: Nền tảng yêu cầu một chu kỳ xử lý dữ liệu theo lịch trình để phát hiện các bất thường về chi phí. Nhóm phát triển phải cân bằng giữa tốc độ phát hiện với độ trễ xuất hóa đơn của AWS (CUR), chi phí API (Cost Explorer), mức tiêu thụ tài nguyên tính toán và nguy cơ cảnh báo giả từ các đột biến chi tiêu tạm thời theo giờ.
- **Quyết định (Decision)**: Chọn chu kỳ xử lý 24 giờ cho pipeline FinOps được lập lịch, được kích hoạt hàng ngày bởi EventBridge Scheduler.
- **Hệ quả (Consequence)**:
  - Pro: Căn chỉnh hoàn hảo với chu kỳ cập nhật 24 giờ của AWS CUR và dữ liệu tổng hợp từ Cost Explorer, tránh các lượt chạy trùng lặp không cần thiết.
  - Pro: Giảm đáng kể chi phí truy vấn và thời gian tính toán so với chu kỳ 12 giờ hoặc hàng giờ.
  - Pro: Giảm thiểu cảnh báo giả từ việc tự động mở rộng quy mô tài nguyên tạm thời trong ngày vốn sẽ tự động được giải quyết trong vòng một ngày làm việc.
  - Trade-off: Thời gian tối đa để phát hiện bất thường là 24 giờ, điều này có thể dẫn đến thất thoát chi phí cao hơn đối với các đột biến chi tiêu đột ngột và lớn.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Chu kỳ 12 giờ (12h cadence): Bị từ chối vì dữ liệu hóa đơn AWS (CUR) không được cập nhật đủ thường xuyên để biện minh cho việc nhân đôi chi phí API và các lượt chạy tính toán.
  - Chu kỳ 48 giờ (48h cadence): Bị từ chối vì độ trễ phát hiện 2 ngày khiến tổ chức phải đối mặt với sự lãng phí tài chính quá mức trước khi các chính sách containment có thể được đề xuất.

---

## ADR-002 - Kiến trúc dữ liệu tập trung vào hồ dữ liệu (Lakehouse-centric FinOps control plane architecture)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: Nền tảng phải thu thập, phân vùng, phân tích và báo cáo khối lượng lớn dữ liệu chi phí AWS. Kho lưu trữ dữ liệu phải có khả năng mở rộng tốt, hiệu quả về chi phí cho lưu trữ dài hạn và hỗ trợ các truy vấn SQL ad-hoc mà không yêu cầu máy chủ cơ sở dữ liệu hoạt động liên tục.
- **Quyết định (Decision)**: Triển khai một data plane tập trung vào hồ dữ liệu (lakehouse) sử dụng Amazon S3 để lưu trữ dữ liệu raw và curated, AWS Glue Data Catalog để ánh xạ metadata và Amazon Athena cho việc truy vấn SQL serverless.
- **Hệ quả (Consequence)**:
  - Pro: Mô hình serverless đồng nghĩa với việc không có chi phí hạ tầng nhàn rỗi cho lớp truy vấn.
  - Pro: Các chính sách lifecycle của S3 có thể tự động lưu trữ các phân vùng CUR lịch sử vào Glacier, giảm thiểu chi phí lưu trữ dài hạn.
  - Pro: Khả năng mở rộng cao, hỗ trợ các truy vấn phân tích trên hàng triệu bản ghi chi phí.
  - Trade-off: Các truy vấn Athena có độ trễ khởi động truy vấn (cold start) vài giây, khiến chúng không phù hợp cho các truy vấn web giao dịch theo thời gian thực (được giảm thiểu bằng cách sử dụng DynamoDB cho bảng điều khiển và tra cứu giao dịch).
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Cơ sở dữ liệu quan hệ (RDS PostgreSQL): Bị từ chối do chi phí vận hành cao cho các instance cơ sở dữ liệu luôn chạy và việc mở rộng dung lượng lưu trữ phức tạp khi xử lý dữ liệu hóa đơn lịch sử khổng lồ.
  - Chỉ sử dụng NoSQL (DynamoDB): Bị từ chối do thiếu khả năng phân tích phức tạp, các chức năng join và các công cụ phân vùng để phân tích CUR.

---

## ADR-003 - Ranh giới trách nhiệm giữa CDO và AIOps (CDO/AIOps responsibility boundary)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: Cần phân chia công việc rõ ràng giữa nhóm CDO (vận hành nền tảng và pipeline) và nhóm AIOps (phát triển AI engine) để ngăn ngừa các nỗ lực trùng lặp, thiết lập quyền sở hữu và xác định các SLA vận hành.
- **Quyết định (Decision)**: Thiết lập tích hợp dựa trên hợp đồng nghiêm ngặt. CDO sở hữu việc thu thập dữ liệu chi phí, các luồng công việc theo lịch trình, cảnh báo, thực thi containment và hạ tầng nền tảng lưu trữ (ECS cluster, capacity providers, networking) cho AI Engine. AIOps sở hữu logic AI Engine, container image, các tham số mô hình, tính toán điểm độ tin cậy và các chỉ số backtesting.
- **Hệ quả (Consequence)**:
  - Pro: Các chu kỳ phát hành độc lập và cách ly trách nhiệm. Quyền sở hữu rõ ràng để xử lý sự cố.
  - Pro: Hợp đồng chuẩn hóa ngăn ngừa các thay đổi gây phá vỡ khi mô hình AI được cập nhật.
  - Trade-off: Yêu cầu duy trì một hợp đồng tích hợp có phiên bản và các mock endpoints cho việc kiểm thử cục bộ.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Mô hình nhóm nguyên khối (Monolithic team model): Bị từ chối vì nó làm mờ các ranh giới kỹ thuật và gây khó khăn cho việc mở rộng quy mô vận hành nền tảng và các hướng tinh chỉnh mô hình riêng biệt.
  - AIOps tự host dịch vụ của họ: Bị từ chối vì CDO cần kiểm soát chặt chẽ mạng, bảo mật IAM và tích hợp containment trong landing zone đám mây chính.

---

## ADR-004 - Truy cập dữ liệu qua CUR S3 kết hợp với Cost Explorer API (CUR S3 plus Cost Explorer API data access)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: Nền tảng yêu cầu cả các chỉ số chi phí chi tiết ở cấp tài nguyên (có cấu trúc cao) và các truy vấn dữ liệu chi phí theo thời gian thực hoặc gần thời gian thực để bắt các mô hình bất thường.
- **Quyết định (Decision)**: Kết hợp AWS Data Exports (CUR 2.0) được phân phối tới S3 với các truy vấn trực tiếp đến AWS Cost Explorer API. CUR được sử dụng cho việc phân tích sâu lịch sử, phân tích phân vùng và các xu hướng trên bảng điều khiển, trong khi Cost Explorer API phục vụ như cơ chế truy vấn gần thời gian thực chính cho các lượt chạy hàng ngày. Để tránh vượt quá giới hạn tần suất nghiêm ngặt **5 requests/second** của Cost Explorer, CDO thực hiện cache kết quả truy vấn vào DynamoDB; AI Engine tiêu thụ dữ liệu cost đã cache này khi cần dữ liệu baseline 7 ngày và 30 ngày thay vì gọi trực tiếp Cost Explorer API.
- **Hệ quả (Consequence)**:
  - Pro: CUR cung cấp các bản ghi cấp tài nguyên chi tiết cho việc kiểm toán và hiển thị trên bảng điều khiển.
  - Pro: Cost Explorer API cung cấp dữ liệu độ trễ thấp cho khoảng thời gian 24 giờ qua, bỏ qua độ trễ xuất của CUR.
  - Pro: Cache dữ liệu chi phí vào DynamoDB giúp tránh các vấn đề giới hạn tần suất gọi API (rate-limiting) và đảm bảo quyền truy cập ngoại tuyến ổn định cho AI Engine.
  - Trade-off: Giới thiệu các sai lệch nhỏ giữa các bản ghi CUR cuối cùng và kết quả đầu ra của Cost Explorer API thời gian thực do độ trễ đối soát của AWS.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Chỉ sử dụng CUR (CUR only): Bị từ chối vì các bản xuất CUR có độ trễ cố định từ 8 đến 24 giờ, vi phạm các yêu cầu về độ tươi mới của dữ liệu cho việc phát hiện hàng ngày.
  - Chỉ sử dụng Cost Explorer API (Cost Explorer API only): Bị từ chối vì việc truy vấn khối lượng lớn dữ liệu lịch sử ở cấp tài nguyên qua API rất tốn kém và bị giới hạn tần suất gọi nghiêm ngặt.

---

## ADR-005 - Chính sách containment ưu tiên giả lập trước (Dry-run-first containment guardrail)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: Các hành động containment tự động ngoài ý muốn trong môi trường sản xuất (như dừng node, thay đổi quota hoặc sửa đổi cài đặt bảo mật) có thể gây ra thời gian ngừng hoạt động kinh doanh nghiêm trọng.
- **Quyết định (Decision)**: Triển khai chính sách containment "dry-run-first" trên tất cả các môi trường. Trong môi trường sản xuất (production), containment được giới hạn nghiêm ngặt ở chế độ dry-run (giả lập, gắn tag để xem xét hoặc đưa ra đề xuất). Trong môi trường phát triển (development) và sandbox, các hành động tự động (như tắt tài nguyên) có thể được áp dụng chỉ sau khi xác minh chính sách và tạo bản ghi kiểm toán.
- **Hệ quả (Consequence)**:
  - Pro: Không có rủi ro ngừng hoạt động tự động trong các khối lượng công việc sản xuất do phát hiện cảnh báo giả.
  - Pro: Vẫn cung cấp khả năng hiển thị đầy đủ về những gì hệ thống lẽ ra đã thực hiện.
  - Trade-off: Yêu cầu sự can thiệp của con người để thực thi các bước khắc phục thực tế trên môi trường sản xuất, làm kéo dài một chút thời gian khắc phục (time-to-remediate).
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Tự động hóa hoàn toàn ở mọi nơi: Bị từ chối do rủi ro gián đoạn kinh doanh không thể chấp nhận được.
  - Chỉ gửi thông báo thủ công: Bị từ chối vì môi trường phát triển và sandbox được hưởng lợi từ containment tự động để ngăn ngừa lãng phí ngân sách.

---

## ADR-006 - Nhật ký kiểm toán DynamoDB/S3 với thời gian lưu trữ ít nhất 90 ngày (DynamoDB/S3 audit trail with >=90 days retention)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: Tuân thủ tài chính yêu cầu một bản ghi không thể giả mạo và bền vững về tất cả các hành động containment tự động và được đề xuất, phải được giữ lại cho mục đích kiểm toán.
- **Quyết định (Decision)**: Triển khai một nhật ký kiểm toán hai lớp lưu trữ các bản ghi kiểm toán containment trong DynamoDB (cho việc truy vấn dashboard độ trễ thấp) và S3 có bật Object Lock (cho lưu trữ tuân thủ dài hạn), thực thi thời gian lưu trữ tối thiểu là 90 ngày.
- **Hệ quả (Consequence)**:
  - Pro: Khả năng truy xuất nguồn gốc hoàn chỉnh của các quyết định tự động cho các cuộc kiểm toán tài chính.
  - Pro: S3 Object Lock ngăn chặn việc vô tình xóa hoặc sửa đổi các bản ghi.
  - Trade-off: Độ phức tạp lưu trữ và dung lượng mã nguồn cao hơn một chút để ghi vào hai mục tiêu cơ sở dữ liệu.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Chỉ sử dụng DynamoDB: Bị từ chối vì các bảng DynamoDB không hỗ trợ mặc định các tính năng tuân thủ Object Lock (Write Once Read Many - WORM).
  - Chỉ sử dụng CloudWatch Logs: Bị từ chối vì việc phân tích cú pháp nhật ký CloudWatch chậm và không phù hợp để hiển thị trực tiếp trên các bảng điều khiển tài chính hướng tới người dùng.

---

## ADR-007 - Sử dụng ECS Fargate để host AI Engine (ECS Fargate for AI Engine hosting)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: AI Engine do nhóm AIOps cung cấp được đóng gói dưới dạng một ứng dụng python container hóa yêu cầu sự linh hoạt về CPU/memory, thực thi cô lập và bảo mật mạng.
- **Quyết định (Decision)**: Triển khai và host các khối lượng công việc container AI Engine trên AWS ECS (Elastic Container Service) với Fargate.
- **Hệ quả (Consequence)**:
  - Pro: Mô hình tính toán serverless loại bỏ nhu cầu quản lý các instance EC2 hoặc các node Kubernetes.
  - Pro: Các vai trò IAM ở cấp tác vụ (task-level IAM roles) cô lập các quyền, và các tác vụ được chạy trong các private subnets đằng sau internal ALB.
  - Trade-off: Thời gian khởi động nguội (cold start) cao hơn so với các máy ảo luôn chạy (được giảm thiểu bằng cách sử dụng các capacity provider luôn hoạt động cho các tác vụ API/explainer).
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - AWS Lambda: Bị từ chối vì kích thước thư viện mô hình AI (ví dụ: pandas, scikit-learn, PyTorch) vượt quá giới hạn gói triển khai của Lambda và thời gian chạy có thể vượt quá giới hạn thực thi 15 phút của Lambda.
  - Amazon EKS (Kubernetes): Bị từ chối do độ phức tạp vận hành cao và chi phí chạy tối thiểu của cụm (cluster), điều này không được biện minh cho khối lượng công việc đơn lẻ này.

---

## ADR-008 - Tách biệt giữa capacity provider Fargate luôn hoạt động và Fargate Spot (Fargate always-on vs Fargate Spot capacity providers separation)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: AI Engine thực thi cả các tác vụ API độ trễ thấp (health checks, giải thích bất thường cho bảng điều khiển) và các khối lượng công việc hàng loạt (batch workloads) có thể bị gián đoạn và đòi hỏi nhiều tài nguyên tính toán (chạy chấm điểm bất thường hàng ngày, huấn luyện lại mô hình).
- **Quyết định (Decision)**: Tách biệt việc thực thi tác vụ ECS trên các capacity provider Fargate. Sử dụng Fargate tiêu chuẩn luôn hoạt động (always-on) cho các tác vụ API explainer, và Fargate Spot cho các tác vụ phân tích hàng loạt, huấn luyện lại và feature engineering.
- **Hệ quả (Consequence)**:
  - Pro: Giảm chi phí tính toán lên tới 70% cho các tác vụ chạy hàng loạt và huấn luyện lại bằng cách sử dụng Fargate Spot.
  - Pro: Capacity provider luôn hoạt động đảm bảo dashboard API luôn khả dụng và phản hồi nhanh chóng.
  - Trade-off: Các công việc hàng loạt phải triển khai các điểm lưu trạng thái (checkpoints) và logic thử lại để xử lý các sự kiện gián đoạn tác vụ Fargate Spot một cách mềm dẻo.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Fargate luôn hoạt động cho tất cả các tác vụ: Bị từ chối vì nó dẫn đến chi phí tính toán nhàn rỗi quá mức trong các đợt chạy hàng loạt lớn hoặc chạy huấn luyện lại mô hình.
  - Fargate Spot cho tất cả các tác vụ: Bị từ chối vì sự gián đoạn spot trên các tác vụ API/explainer sẽ làm gián đoạn tính khả dụng của bảng điều khiển và các SLO cảnh báo thời gian thực.

---

## ADR-009 - Điểm cuối AI Engine dùng chung cho Task Force (Shared Task Force AI Engine endpoint)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: Task Force 2 vận hành hai nền tảng FinOps CDO độc lập (CDO-01 và CDO-02) đại diện cho các đơn vị kinh doanh khác nhau. Để giảm thiểu chi phí vận hành và đơn giản hóa việc quản lý mô hình, chúng tôi cần một kiến trúc triển khai cho AIOps AI Engine để host một lần duy nhất nhưng vẫn phục vụ cả hai nền tảng CDO một cách an toàn và hiệu quả.
- **Quyết định (Decision)**: Triển khai một điểm cuối AI Engine dùng chung duy nhất được host trên ECS Fargate trong một VPC dùng chung, có thể truy cập nội bộ thông qua `https://ai-engine.tf-2.internal/` với xác thực IAM SigV4. Sự cô lập đa người thuê (multi-tenant) được duy trì thông qua header `X-Tenant-Id` của yêu cầu để phân vùng dữ liệu và các yêu cầu.
- **Phân chia trách nhiệm (Responsibility Split)**:
  - **CDO** sở hữu việc triển khai hạ tầng host: Mạng VPC (subnets, route tables, VPC endpoints), bộ cân bằng tải nội bộ (Internal Application Load Balancer - ALB), cấu hình bản ghi DNS, cấu hình cụm ECS cluster, chính sách tự động mở rộng quy mô tác vụ (scaling policies), các Security Groups, các ECS Task Execution và IAM Roles, hàng đợi xử lý SQS, và kho lưu trữ trạng thái chạy/idempotency trên DynamoDB.
  - **AIOps** sở hữu logic ứng dụng bên trong container: Mã nguồn mô hình AI, quy trình đóng gói và phát hành container image (ECR image payload), logic Phân tích Nguyên nhân Gốc rễ (RCA) và khuyến nghị khắc phục, thực thi rules engine dự phòng cục bộ, tuân thủ hợp đồng API nội bộ, và theo dõi baseline đánh giá (evaluation baseline).
- **Hệ quả (Consequence)**:
  - Pro: Giảm đáng kể chi phí vận hành bằng cách chỉ host một cụm ECS Fargate dùng chung duy nhất thay vì các cụm riêng biệt cho từng nền tảng CDO.
  - Pro: Đơn giản hóa việc quản lý phát hành và cập nhật mô hình cho AIOps vì họ chỉ cần xuất bản một phiên bản duy nhất của container image.
  - Pro: Truy cập điểm cuối trực tiếp bằng DNS nội bộ AWS (`https://ai-engine.tf-2.internal/`) đảm bảo lưu lượng truy cập không bao giờ đi qua internet công cộng, đáp ứng các NFR bảo mật.
  - Trade-off: Yêu cầu sự phối hợp chặt chẽ giữa CDO và AIOps để cấu hình kích thước tác vụ và tự động co giãn, cũng như cấu hình nghiêm ngặt các header tenant để tránh rò rỉ dữ liệu giữa các bên.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Mỗi nền tảng CDO có một AI Engine riêng biệt (Separate AI Engine per CDO Platform): Bị từ chối do chi phí tài nguyên trùng lặp và chi phí bảo trì cao cho việc quản lý phiên bản mô hình và triển khai container.
  - Điểm cuối HTTP công cộng với API Gateway: Bị từ chối vì xác thực dựa trên IAM SigV4 qua bộ cân bằng tải nội bộ riêng tư mang lại bảo mật truyền tải mạnh mẽ hơn và độ trễ thấp hơn mà không để lộ điểm cuối ra internet.
