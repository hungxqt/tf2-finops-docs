# Quyết định Thiết kế Kiến trúc (Architecture Decision Records) - FinOps Watch CDO · Task Force 2

<!-- Doc owner: CDO Team
     Status: Ongoing log W11-W12
     Format: 1 ADR per major decision. Append-only - do not delete old ADRs. -->

> **Ranh giới Bảo mật**: Mọi quyết định thiết kế và mô hình kiến trúc phải tuân thủ nghiêm ngặt ranh giới cứng: **NEVER terminate prod, delete data, hoặc modify IAM**.

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
  - Chu kỳ 12 giờ (12h cadence): Bị từ chối vì dữ liệu hóa đơn AWS (CUR) không được cập nhật đủ thường xuyên để biên minh cho việc nhân đôi chi phí API và các lượt chạy tính toán.
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
- **Quyết định (Decision)**: Thiết lập tích hợp dựa trên hợp đồng nghiêm ngặt. CDO sở hữu việc thu thập dữ liệu chi phí, các luồng công việc theo lịch trình, cảnh báo, thực thi containment và hạ tầng nền tảng lưu trữ (các hàm Lambda container, triển khai ghim digest ECR, các vai trò thực thi IAM, reserved concurrency, SQS/DLQ, các kho lưu trữ DynamoDB/S3, mạng và SLO) cho AI Engine. AIOps sở hữu logic AI Engine, container image, các tham số mô hình, tính toán điểm độ tin cậy và các chỉ số backtesting.
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
- **Bối cảnh (Context)**: Nền tảng yêu cầu cả các chỉ số chi phí chi tiết ở cấp tài nguyên (có cấu trúc cao) và các truy vấn dữ liệu chi phí hàng ngày để bắt các mô hình bất thường.
- **Quyết định (Decision)**: Kết hợp AWS Data Exports (CUR 2.0) được phân phối tới S3 với các truy vấn trực tiếp đến AWS Cost Explorer API. CUR được sử dụng cho việc phân tích sâu lịch sử, phân tích phân vùng và các xu hướng trên bảng điều khiển, trong khi Cost Explorer API phục vụ như cơ chế truy vấn hàng ngày chính cho các lượt chạy theo lịch. Để tránh vượt quá giới hạn tần suất nghiêm ngặt **5 requests/second** của Cost Explorer, CDO thực hiện cache kết quả truy vấn vào DynamoDB; AI Engine tiêu thụ dữ liệu cost đã cache này khi cần dữ liệu baseline 7 ngày và 30 ngày thay vì gọi trực tiếp Cost Explorer API.
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

- **Trạng thái (Status)**: Partially Superseded by ADR-016
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

## ADR-007 - ECS Fargate để host AI Engine thay vì các hàm serverless (ECS Fargate for AI Engine hosting over serverless functions)

- **Trạng thái (Status)**: Superseded by ADR-010
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: AI Engine do nhóm AIOps cung cấp được đóng gói dưới dạng một ứng dụng python container hóa, yêu cầu sự linh hoạt về CPU/memory, thực thi cách ly và bảo mật mạng.
- **Quyết định (Decision)**: Triển khai và host các workload container của AI Engine trên AWS ECS (Elastic Container Service) chạy Fargate.
- **Hệ quả (Consequence)**:
  - Pro: Mô hình tính toán serverless loại bỏ việc quản lý các instance EC2 hoặc node K8s.
  - Pro: Các vai trò IAM ở cấp task (task-level) giúp cô lập quyền, và các task chạy trong subnet riêng tư phía sau ALB nội bộ.
  - Trade-off: Thời gian khởi động nguội (cold start) cao hơn so với máy ảo VM luôn hoạt động (được giảm thiểu bằng cách sử dụng các capacity provider luôn hoạt động cho các tác vụ API/explainer).
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - AWS Lambda: Bị từ chối vì kích thước thư viện mô hình AI (ví dụ: pandas, scikit-learn, PyTorch) vượt quá giới hạn gói triển khai Lambda và thời gian chạy có thể vượt quá giới hạn thực thi 15 phút của Lambda.
  - Amazon EKS (Kubernetes): Bị từ chối do độ phức tạp vận hành cao và chi phí chạy tối thiểu của cụm (cluster) không tương xứng với một workload duy nhất này.

---

## ADR-008 - Tách biệt tác vụ Fargate chạy liên tục và Fargate Spot (Always-on plus Spot Fargate task separation)

- **Trạng thái (Status)**: Superseded by ADR-010
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: AI Engine thực hiện cả các tác vụ API độ trễ thấp (kiểm tra sức khỏe, giải thích bất thường cho bảng điều khiển) và các tác vụ theo lô chuyên sâu về tính toán có thể bị gián đoạn (chấm điểm bất thường hàng ngày, huấn luyện lại mô hình).
- **Quyết định (Decision)**: Tách biệt việc thực thi các tác vụ ECS trên các Fargate capacity provider khác nhau. Sử dụng Fargate tiêu chuẩn (always-on) cho các tác vụ API explainer, và Fargate Spot capacity provider cho các tác vụ phân tích theo lô, huấn luyện lại và chuẩn bị đặc trưng (feature engineering).
- **Hệ quả (Consequence)**:
  - Pro: Giảm chi phí tính toán lên đến 70% cho các tác vụ theo lô và huấn luyện lại bằng cách sử dụng Fargate Spot.
  - Pro: Capacity provider always-on đảm bảo API bảng điều khiển có tính sẵn sàng cao và phản hồi nhanh chóng.
  - Trade-off: Các tác vụ theo lô phải thiết lập điểm kiểm tra (checkpoint) và logic thử lại để xử lý sự kiện gián đoạn của Fargate Spot một cách trơn tru.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Fargate always-on cho tất cả tác vụ: Bị từ chối vì dẫn đến chi phí tính toán nhàn rỗi quá mức trong các đợt chạy lô lớn hoặc huấn luyện lại mô hình.
  - Fargate Spot cho tất cả tác vụ: Bị từ chối vì sự gián đoạn của Spot đối với các tác vụ API/explainer sẽ phá vỡ tính sẵn sàng của dashboard và các SLO cảnh báo thời gian thực.

---

## ADR-009 - Endpoint AI Engine dùng chung cho Task Force (Shared Task Force AI Engine endpoint)

- **Trạng thái (Status)**: Superseded by ADR-011
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: Task Force 2 vận hành hai nền tảng CDO riêng biệt (CDO-01 and CDO-02) đại diện cho các đơn vị kinh doanh khác nhau. Để giảm thiểu chi phí vận hành và đơn giản hóa việc quản lý mô hình, chúng tôi cần một kiến trúc triển khai cho AI Engine của AIOps để host nó một lần duy nhất trong khi vẫn phục vụ cả hai nền tảng CDO một cách an toàn và hiệu quả.
- **Quyết định (Decision)**: Triển khai một endpoint AI Engine dùng chung duy nhất cho Task Force được host trên ECS Fargate trong một VPC dùng chung, có thể truy cập nội bộ qua `https://ai-engine.tf-2.internal/` sử dụng xác thực IAM SigV4. Việc cô lập đa người thuê (multi-tenant isolation) được duy trì thông qua header `X-Tenant-Id` của yêu cầu để phân vùng dữ liệu và các cuộc gọi.
- **Phân chia trách nhiệm (Responsibility Split)**:
  - CDO sở hữu việc triển khai hạ tầng host: mạng VPC (subnets, route tables, VPC endpoints), Bộ cân bằng tải ứng dụng nội bộ (internal ALB), cấu hình bản ghi DNS, cấu hình cụm ECS, chính sách co giãn task, Security Groups, ECS Task Execution và IAM Roles, hàng đợi xử lý SQS, và kho lưu trữ trạng thái thực thi/idempotency trên DynamoDB.
  - AIOps sở hữu logic ứng dụng bên trong container: mã nguồn mô hình AI, quy trình đóng gói và xuất bản container image (ECR image payload), logic Phân tích Nguyên nhân Gốc rễ (RCA) và khuyến nghị khắc phục, thực thi rules engine dự phòng cục bộ, tuân thủ hợp đồng API nội bộ, và theo dõi đánh giá baseline.
- **Hệ quả (Consequence)**:
  - Pro: Giảm đáng kể chi phí vận hành bằng cách chỉ host một cụm ECS Fargate dùng chung thay vì các cụm riêng biệt cho từng nền tảng CDO.
  - Pro: Đơn giản hóa việc quản lý phát hành và cập nhật mô hình cho AIOps vì họ chỉ xuất bản một phiên bản duy nhất của container image.
  - Pro: Truy cập endpoint trực tiếp bằng DNS riêng của AWS (`https://ai-engine.tf-2.internal/`) đảm bảo lưu lượng truy cập không bao giờ đi qua internet công cộng, đáp ứng các NFR về bảo mật.
  - Trade-off: Yêu cầu sự phối hợp giữa CDO và AIOps để cấu hình kích thước task và tự động co giãn, cũng như cấu hình nghiêm ngặt các header người thuê để tránh rò rỉ dữ liệu chéo.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - AI Engine riêng cho mỗi nền tảng CDO: Bị từ chối do trùng lặp chi phí tài nguyên và chi phí bảo trì cao cho phiên bản mô hình và triển khai container.
  - Endpoint HTTP công cộng với API Gateway: Bị từ chối vì xác thực SigV4 qua bộ cân bằng tải riêng tư nội bộ cung cấp khả năng bảo mật truyền tải mạnh mẽ hơn và độ trễ thấp hơn mà không để lộ endpoint ra internet.

---

## ADR-010 - Host thời gian chạy suy luận AI Engine trên AWS Lambda container (AWS Lambda container image hosting for AI Engine inference)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: AI Engine do nhóm AIOps cung cấp được đóng gói dưới dạng ứng dụng python container hóa, yêu cầu sự linh hoạt về CPU/memory, thực thi độc lập, và bảo mật mạng. Quyết định trước đó sử dụng ECS Fargate (ADR-007) và capacity provider Fargate Spot (ADR-008) phát sinh chi phí nền tảng cố định dùng chung (máy chủ chạy nhàn rỗi, bộ cân bằng tải) và tăng độ phức tạp vận hành (ghi nhận checkpoint, gián đoạn Spot).
- **Quyết định (Decision)**: Triển khai và host một instance độc lập, dành riêng cho mỗi CDO (per-CDO) của workload container AI Engine trên AWS Lambda sử dụng container images, thay vì chia sẻ một host duy nhất (shared host ONCE) trong toàn bộ Task Force. CDO này tự vận hành endpoint/platform riêng của mình, sử dụng Lambda Container images được xây dựng từ kho lưu trữ ECR do nhóm AIOps bàn giao. Quy trình triển khai sử dụng cơ chế ghim digest ECR (bằng cách ghim mã SHA digest cụ thể của image trong Terraform) để đảm bảo tính bất biến khi thực thi. CDO triển khai bộ đệm SQS (SQS buffering) để thực thi tác vụ không đồng bộ một cách tin cậy và cấu hình giới hạn concurrency dành riêng cho Lambda (Lambda reserved concurrency limits) (giới hạn ở trần thực thi an toàn) nhằm ngăn ngừa đột biến quy mô làm nghẽn các tài nguyên khác, duy trì ranh giới mạng riêng tư, và kiểm soát phạm vi ảnh hưởng (blast radius) vận hành.
- **Hệ quả (Consequence)**:
  - Pro: Mô hình thanh toán trả tiền theo yêu cầu thực tế giúp giảm chi phí chạy nhàn rỗi cố định của ECS Fargate về mức 0.
  - Pro: Tính sẵn sàng cao và tự động co giãn được quản lý gốc bởi AWS thông qua việc thực thi Lambda container image.
  - Pro: Bộ đệm hàng đợi SQS giúp xử lý các thời điểm đột biến cuộc gọi mà không bị mất dữ liệu yêu cầu thực thi.
  - Pro: Việc ghim digest ECR đảm bảo các thay đổi mã nguồn bắt buộc phải qua một bộ thay đổi Terraform rõ ràng, tránh trôi lệch (drift) cấu hình.
  - Trade-off: Có thể xảy ra độ trễ khởi động nguội (cold start) đối với container image (giảm thiểu bằng Provisioned Concurrency nếu độ trễ thực tế vượt quá ngưỡng SLA sản xuất).
  - Trade-off: Kích thước container image phải nằm trong giới hạn 10 GB của Lambda; việc tái huấn luyện mô hình phải được thực hiện ngoại tuyến.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - ECS Fargate always-on + Spot: Bị từ chối vì chi phí chạy nhàn rỗi cao và yêu cầu checkpoint/retry phức tạp.
  - Gói zip AWS Lambda tiêu chuẩn: Bị từ chối vì kích thước thư viện mô hình AI (như pandas, scikit-learn, PyTorch) vượt quá giới hạn 250MB (khi giải nén) của gói zip Lambda.

---

## ADR-011 - Sử dụng Private REST API Gateway thay thế cho internal ALB (Private REST API Gateway over internal ALB)

- **Trạng thái (Status)**: Superseded by ADR-012
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: API của AI Engine phải được truy cập một cách an toàn và riêng tư bởi nhiều nền tảng CDO trong mạng nội bộ. Quyết định trước đó sử dụng một internal ALB (ADR-009). Tuy nhiên, khi chuyển sang host trên AWS Lambda container, việc sử dụng REST API Gateway với tích hợp Lambda là lựa chọn tự nhiên và an toàn hơn cho việc công khai API nội bộ.
- **Quyết định (Decision)**: Công khai endpoint AI Engine dùng chung qua Private REST API Gateway sử dụng xác thực IAM SigV4 và tích hợp Lambda proxy/container. Sự cô lập đa người thuê (multi-tenant) được duy trì thông qua header `X-Tenant-Id` của yêu cầu để phân vùng dữ liệu và các yêu cầu.
- **Phân chia trách nhiệm (Responsibility Split)**:
  - CDO sở hữu hạ tầng host: Mạng VPC, tài nguyên Private REST API Gateway, tham số stage/deployment, role execution IAM, các hàng đợi xử lý SQS, và DynamoDB lưu trạng thái chạy/idempotency.
  - AIOps sở hữu logic ứng dụng bên trong Lambda container: Mã nguồn mô hình AI, quy trình đóng gói/phát hành container image (ECR image payload), logic Phân tích Nguyên nhân Gốc rễ (RCA) và khuyến nghị khắc phục, thực thi rules engine dự phòng cục bộ, tuân thủ hợp đồng API nội bộ, và theo dõi baseline đánh giá.
- **Hệ quả (Consequence)**:
  - Pro: Kết nối API nội bộ an toàn qua VPC endpoint, tránh được chi phí thuê hàng giờ của ALB.
  - Pro: Tích hợp sẵn IAM SigV4 cho việc xác thực mạnh mẽ.
  - Pro: Hỗ trợ sẵn các tính năng throttling API, biến môi trường của stage, và định tuyến.
  - Pro: Tích hợp tự nhiên với API Gateway Resource Policies để thực thi cô lập multi-tenant.
  - Trade-off: Private API Gateway yêu cầu cấp phát VPC Endpoint riêng, tuy nhiên các endpoint này có thể chia sẻ dùng chung với các dịch vụ khác của nền tảng.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Định tuyến qua Internal ALB: Bị từ chối vì API Gateway cung cấp khả năng quản lý endpoint, rate limiting tốt hơn và tích hợp proxy Lambda gốc tối ưu cho serverless runtime.
  - Endpoint HTTP công cộng với API Gateway: Bị từ chối vì xác thực SigV4 qua private endpoint đảm bảo lưu lượng không đi qua internet công cộng, đáp ứng NFR về bảo mật.

---

## ADR-012 - Gọi trực tiếp Lambda/SQS cho AI Engine thay vì qua Private API Gateway (Direct Lambda/SQS AI Engine invocation over Private API Gateway)

- **Trạng thái (Status)**: Superseded by ADR-018
- **Ngày (Date)**: 2026-06-24
- **Bối cảnh (Context)**: Luồng chạy CDO hiện tại là một quy trình xử lý theo lô (batch workflow) được lập lịch, điều phối bởi EventBridge Scheduler và Step Functions. Hợp đồng API v1.1 của AI yêu cầu các ngữ nghĩa hợp đồng logic `/v1/detect`, `/v1/status/{id}`, `/v1/decide`, `/v1/verify`, và `/v1/audit/{audit_id}/rollback`, nhưng kiến trúc không cần đến một Private REST API Gateway riêng biệt khi Step Functions là caller điều phối duy nhất.
- **Quyết định (Decision)**: Tránh triển khai một Private REST API Gateway vật lý cho luồng chạy lô (batch workflow) lập lịch mặc định, do Step Functions đóng vai trò là caller điều phối duy nhất. Thay vào đó, các giao diện `/v1/detect`, `/v1/status/{id}`, `/v1/decide`, và `/v1/verify` được triển khai thuần túy dưới dạng ngữ nghĩa hợp đồng logic (logical contract semantics). Dưới hạ tầng, Step Functions gọi trực tiếp AI Engine Request Lambda cho `/v1/detect`, hàm này xác thực dữ liệu và đẩy vào hàng đợi SQS để trả về token thực thi nhanh. AI Engine Worker Lambda sẽ xử lý bất đồng bộ hàng đợi, lưu kết quả phát hiện bất thường vào DynamoDB và S3. Quy trình Step Functions thực hiện polling `/v1/status/{correlation_id}` cho đến khi hoàn tất, sau đó gọi `/v1/decide` để lập kế hoạch can thiệp, thực thi các hành động can thiệp đã phê duyệt, và gọi `/v1/verify` để xác minh kết quả. Endpoint rollback `/v1/audit/{audit_id}/rollback` được gọi khi cần hoàn tác thủ công. Private API Gateway bị từ chối trong nền tảng CDO cơ sở để giảm tải chi phí và độ phức tạp dư thừa, chỉ tồn tại như một lựa chọn thiết kế tùy chọn cho việc triển khai đa client trong tương lai.
- **Hệ quả (Consequence)**:
  - Pro: Loại bỏ chi phí khởi tạo hạ tầng và quản lý của API Gateway stage, usage plan, resource policy tùy chỉnh, và VPC Endpoint chuyên dụng.
  - Pro: Giữ cho luồng chạy lô 24 giờ theo lịch trình hoàn toàn serverless, trực tiếp và bảo mật.
  - Pro: Bảo toàn được hợp đồng logic và ranh giới chạy container của AI Engine từ AIOps.
  - Trade-off: Các hệ thống nội bộ khác không thể gọi truy vấn AI Engine thông qua yêu cầu HTTP REST theo mặc định.
  - Trade-off: Các cơ chế điều tiết (throttling), xác thực yêu cầu, và định tuyến môi trường phải được xử lý ở lớp ứng dụng Lambda và phân quyền AWS IAM.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Giữ lại Private REST API Gateway: Bị từ chối đối với luồng mặc định vì nó tăng thêm tài nguyên hạ tầng mà không mang lại giá trị rõ ràng khi Step Functions là caller duy nhất.
  - Public API Gateway: Bị từ chối vì AI Engine phải được giữ riêng tư và bảo mật nội bộ.
  - Internal ALB: Bị từ chối vì nó nặng nề hơn mức cần thiết đối với việc hosting Lambda container và gọi theo lô theo lịch trình.

---

## ADR-013 - Dashboard S3 + CloudFront thay vì QuickSight cho MVP (S3 + CloudFront dashboard over QuickSight for MVP)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-25
- **Bối cảnh (Context)**: Nền tảng yêu cầu một giao diện người dùng để các bên liên quan từ bộ phận Tài chính giám sát xu hướng chi tiêu, xem các bất thường về chi phí và xem xét các hành động containment. Kiến trúc cần quyết định xem nên sử dụng một dịch vụ BI được quản lý (Amazon QuickSight) hay một trang web tĩnh tự thiết kế được host trên Amazon S3 và phân phối qua Amazon CloudFront cho sản phẩm khả dụng tối thiểu (MVP).
- **Quyết định (Decision)**: Sử dụng một bảng điều khiển tĩnh trên Amazon S3 riêng tư được phân phối qua Amazon CloudFront, xác thực bằng Amazon Cognito (Hosted UI với Luồng mã cấp quyền + PKCE) và bảo vệ bằng S3 Origin Access Control (OAC) và xác thực token Lambda@Edge viewer-request. Amazon QuickSight vẫn được giữ lại như một tùy chọn BI tiềm năng trong tương lai nhưng không được chọn cho baseline của MVP.
- **Hệ quả (Consequence)**:
  - Pro: Chi phí hạ tầng định kỳ thấp hơn do tránh được phí nền tảng cố định của QuickSight Enterprise.
  - Pro: Loại bỏ phí bản quyền trên mỗi người đọc (seat license fees), cho phép mở rộng không giới hạn số lượng người dùng dashboard tài chính mà không phát sinh chi phí cấp phép.
  - Pro: Tích hợp liền mạch với các bản tóm tắt chi phí JSON được tính toán trước do pipeline CDO hàng ngày tạo ra, giúp người dùng dashboard không cần thực thi SQL.
  - Pro: Cho phép kiểm soát chặt chẽ đối với khả năng hiển thị hành động, các nút Kéo dài/Khôi phục (Extend/Rollback) và các tương tác giao diện thông qua logic frontend tự phát triển, điều vốn phức tạp hoặc bị hạn chế trong các công cụ BI gốc.
  - Trade-off: Ít tính năng BI gốc hơn, hạn chế khả năng tự khám phá dữ liệu ad-hoc hoặc tự tạo biểu đồ của người dùng so với QuickSight. Các yêu cầu nâng cao của đơn vị kinh doanh sau này có thể cần tích hợp thêm QuickSight Enterprise.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Amazon QuickSight (Phiên bản Enterprise): Bị từ chối làm mặc định cho MVP do phí seat trên mỗi người dùng, chi phí cấu hình cơ sở cao hơn và sự phức tạp khi nhúng các trình kích hoạt hành động rollback tương tác tùy chỉnh trong các bảng điều khiển tiêu chuẩn.

---

## ADR-014 - Xác thực schema bằng Athena DDL rồi quản lý Glue schema bằng Terraform với Partition Projection (Athena DDL validation to Terraform Glue schema with Partition Projection)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-25
- **Bối cảnh (Context)**: Mặt phẳng dữ liệu lakehouse-centric yêu cầu lập danh mục (catalog) cho các tập dữ liệu Cost and Usage Report (CUR) lưu trữ trên S3. Kiến trúc cần xác định một quy trình quản lý schema đáng tin cậy và chiến lược cập nhật phân vùng để xử lý các thư mục chu kỳ thanh toán được tạo động (ví dụ: year và month) mà không làm tăng độ trễ, gánh nặng thủ công hoặc chi phí chạy thực tế không đáng có.
- **Quyết định (Decision)**: Sử dụng Athena SQL DDL trong quá trình thiết kế và xác thực schema ban đầu vì nó cung cấp phản hồi nhanh chóng đối với các tệp CUR thực tế/giả lập. Sau khi xác thực, chuyển schema này vào các định nghĩa AWS Glue Data Catalog do Terraform quản lý (sử dụng tài nguyên `aws_glue_catalog_table`) như một nguồn sự thật (source of truth) lâu dài. Sử dụng Athena Partition Projection cho các phân vùng chu kỳ thanh toán của CUR/Data Exports để quá trình thu thập theo lịch trình không phụ thuộc vào Glue Crawler, câu lệnh MSCK REPAIR TABLE hoặc đăng ký phân vùng ALTER TABLE thủ công.
- **Hệ quả (Consequence)**:
  - Pro: Loại bỏ hoàn toàn chi phí chạy thực tế ($0,44/DPU-giờ) và độ trễ thực thi (1-3 phút) liên quan đến việc chạy Glue Crawler.
  - Pro: Đảm bảo cấu trúc schema xác định trong Glue Data Catalog, loại bỏ rủi ro sai lệch kiểu dữ liệu hoặc trôi lệch schema (schema drift) do các phỏng đoán (heuristic) của Crawler.
  - Pro: Loại bỏ thông tin xác thực ghi cơ sở dữ liệu hoặc quyền ghi siêu dữ liệu Glue khỏi các hàm Lambda thu thập dữ liệu ở runtime, tuân thủ nguyên tắc đặc quyền tối thiểu.
  - Trade-off: Các bản cập nhật schema yêu cầu thực thi pipeline triển khai thay vì tự động phát hiện ở runtime, điều này phù hợp với các cổng kỹ thuật (engineering gates) ổn định trên môi trường production.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Glue Crawler cho các hoạt động thông thường: Bị từ chối do chi phí DPU, độ trễ chạy và rủi ro schema dựa trên phỏng đoán (heuristic).
  - Athena SQL DDL làm giải pháp quản lý vĩnh viễn: Bị từ chối vì việc tạo schema thủ công gây ra trôi lệch dữ liệu và khó kiểm soát phiên bản hoặc review code hơn so với IaC.
  - Sửa chữa phân vùng thủ công (MSCK REPAIR TABLE hoặc ALTER TABLE được kích hoạt bởi Lambda): Bị từ chối vì nó làm tăng độ trễ vận hành, chi phí gọi API và tính mong manh của lượt chạy theo lịch trình so với tính năng partition projection phía client.

---

## ADR-015 - Hợp đồng phát hiện AI đồng bộ thay vì cơ chế polling hàng đợi trạng thái SQS bất đồng bộ (Synchronous AI detect contract over async SQS status polling)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-25
- **Bối cảnh (Context)**: Hợp đồng của AI Engine Lambda runtime phiên bản v1.1.0 đã chuyển dịch từ mô hình phát hiện bất đồng bộ (trả về `202 Accepted` và yêu cầu polling trên `/v1/status/{correlation_id}`) sang mô hình phát hiện đồng bộ (trả về `200 OK` với danh sách dị thường `anomalies_list` cuối cùng trực tiếp trong phản hồi). Thay đổi hợp đồng API này khiến cho hàng đợi thực thi SQS và logic polling cũ trở nên lỗi thời đối với vòng lặp phát hiện chính.
- **Quyết định (Decision)**: Sử dụng trực tiếp endpoint `/v1/detect` đồng bộ trong workflow điều phối Step Functions của CDO, gọi AI Engine Lambda runtime một cách đồng bộ. Loại bỏ SQS/DLQ khỏi vòng lặp phát hiện chính (chỉ giữ lại SQS cho mục đích retry/backoff cảnh báo). Quyết định này thay thế các phần về luồng phát hiện của ADR-012.
- **Hệ quả (Consequence)**:
  - Pro: Loại bỏ các vòng lặp polling của Step Functions để kiểm tra trạng thái phát hiện, giảm độ phức tạp và số lượng trạng thái thực thi.
  - Pro: Loại bỏ hàng đợi SQS và Dead Letter Queue khỏi đường dẫn tới hạn của quá trình thu thập chi phí và chấm điểm phát hiện, giảm chi phí chạy thực tế và chi phí vận hành nền tảng.
  - Pro: Nhận phản hồi tức thì về sự thành công, correlation ID và danh sách các dị thường trực tiếp từ một payload gọi duy nhất.
  - Trade-off: Thời gian gọi đồng bộ của Step Functions tăng lên, nhưng vẫn nằm trong giới hạn thực thi 15 phút an toàn của AWS Lambda (vì quá trình phân tích CUR và thực thi mô hình Bedrock Nova hoàn tất trong 30-45 giây).
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Giữ lại cơ chế polling SQS bất đồng bộ: Bị từ chối vì hợp đồng API v1.1.0 được đóng băng giữa CDO và AIOps bắt buộc phân phối phản hồi đồng bộ cho route `/v1/detect` để đơn giản hóa việc tích hợp phía client và giảm thiểu sự phình to của hạ tầng AWS.

---

## ADR-016 - Kho lưu trữ kiểm toán và idempotency có thẩm quyền trên S3 (S3 authoritative audit and idempotency store)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-25
- **Bối cảnh (Context)**: Các yêu cầu tuân thủ của chúng tôi đòi hỏi tính bất biến được thực thi bằng phần cứng (WORM) cho nhật ký kiểm toán, trong khi các lượt chạy theo lịch trình của chúng tôi yêu cầu một rào chắn idempotency để tránh xử lý trùng lặp. Chúng tôi cần xác định hệ thống lưu trữ có thẩm quyền cho các tính năng này.
- **Quyết định (Decision)**: Chỉ định S3 là nguồn sự thật có thẩm quyền (authoritative source of truth) cho cả hồ sơ kiểm toán tuân thủ (được lưu trữ trong S3 có bật Object Lock để tuân thủ WORM) và các khóa idempotency (được lưu trữ dưới dạng các đối tượng S3 dưới `s3://company-cdo-telemetry/idempotency/` với chính sách hết hạn vòng đời 24 giờ). DynamoDB bị hạ cấp xuống thành một cache đọc / view truy vấn dashboard không có thẩm quyền. Quyết định này thay thế các phần về nhật ký kiểm toán trên DynamoDB của ADR-006.
- **Hệ quả (Consequence)**:
  - Pro: Đảm bảo tính tuân thủ quy định thực tế (WORM) thông qua tính năng S3 Object Lock gốc, đáp ứng các nguyên tắc kiểm toán nghiêm ngặt mà DynamoDB không thể đáp ứng nếu không có các dịch vụ phụ trợ.
  - Pro: Bằng 0 chi phí dung lượng chạy (RCUs/WCUs) cho lưu trữ kiểm toán dài hạn, chỉ trả tiền cho lưu trữ S3 GB-tháng và số lượng yêu cầu với chi phí thấp.
  - Pro: Idempotency được quản lý thông qua các đối tượng S3 sạch sẽ với chính sách tự động xóa sau 24 giờ.
  - Trade-off: Việc kiểm tra idempotency yêu cầu gọi các hàm S3 HeadObject/GetObject, vốn có độ trễ cao hơn một chút so với tra cứu DynamoDB, mặc dù vẫn không đáng kể đối với tần suất chạy 24 giờ của chúng tôi.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - DynamoDB làm kho lưu trữ kiểm toán có thẩm quyền: Bị từ chối vì DynamoDB không hỗ trợ nguyên bản các ràng buộc write-once-read-many (WORM), vi phạm các NFR tuân thủ nghiêm ngặt.
  - Giữ DynamoDB làm kho lưu trữ idempotency có thẩm quyền: Bị từ chối để đồng nhất kho lưu trữ giao dịch của chúng tôi và đơn giản hóa mã nguồn thu thập của nền tảng CDO, tận dụng các quy tắc lifecycle của S3 để tự động dọn dẹp thay vì quản lý TTL trên DynamoDB.

---

## ADR-017 - Sử dụng AWS Lambda Function URL cho các API endpoint của backend dashboard (Lambda Function URLs for dashboard backend API endpoints)

- **Trạng thái (Status)**: Superseded by ADR-018
- **Ngày (Date)**: 2026-06-25
- **Bối cảnh (Context)**: Nền tảng CDO yêu cầu các endpoint HTTP/HTTPS bảo mật, được xác thực để phục vụ các hành động tương tác trên dashboard (ví dụ: kích hoạt rollback thủ công hoặc xác minh can thiệp) nhằm gọi các hàm Containment Lambda và State Lambda ở backend. Chúng tôi cần quyết định giữa việc triển khai AWS API Gateway (HTTP API) hoặc sử dụng tính năng AWS Lambda Function URL gốc.
- **Quyết định (Decision)**: Triển khai **AWS Lambda Function URL** để cung cấp trực tiếp các endpoint cho các hàm Containment Lambda và State Lambda ở backend. Bảo mật các endpoint này bằng cách định tuyến chúng qua phân phối CloudFront hiện tại và xác thực Cognito session token (JWT) thông qua cổng auth `Lambda@Edge` có sẵn hoặc xác thực trực tiếp trong mã nguồn Lambda.
- **Hệ quả (Consequence)**:
  - Pro: **Vượt qua giới hạn timeout của API Gateway**: Loại bỏ giới hạn timeout tích hợp cứng 30 giây của API Gateway. Luồng xác minh (`POST /v1/verify`) và các hành động rollback có thể chạy đồng bộ tối đa 15 phút nếu cần thiết.
  - Pro: **Bằng 0 chi phí nền tảng**: Function URL hoàn toàn miễn phí (không tính phí yêu cầu hoặc phí triển khai hàng tháng), chỉ tính phí dựa trên tài nguyên compute thực tế của Lambda.
  - Pro: **Đơn giản hóa hạ tầng**: Loại bỏ các cấu hình Terraform phức tạp để quản lý API Gateway routes, deployments, stages, và các tích hợp mapping.
  - Trade-off: Thiếu tính năng liên kết trực tiếp Cognito JWT Authorizer gốc trên tài nguyên. Việc xác thực token phải được triển khai trong mã nguồn Lambda hoặc kiểm tra tại ranh giới của phân phối CloudFront.
  - Trade-off: Mỗi hàm nhận được một URL ngẫu nhiên duy nhất. Điều này được giảm thiểu bằng cách cấu hình các URL này thành các origin path riêng biệt (ví dụ: `/api/containment/*` và `/api/state/*`) đằng sau một phân phối CloudFront duy nhất.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - AWS API Gateway (HTTP API): Bị từ chối vì giới hạn timeout tích hợp 30 giây cứng có thể gây lỗi kết nối cho các tác vụ kiểm tra đồng bộ kéo dài, và để tránh thêm các thành phần hạ tầng không cần thiết vào mặt phẳng điều khiển serverless.

---

## ADR-018 - Sử dụng một container Lambda duy nhất của AIOps để phục vụ các hoạt động hợp đồng AI API (Single AIOps Lambda container serves AI API contract operations)

- **Trạng thái (Status)**: Accepted
- **Ngày (Date)**: 2026-06-25
- **Bối cảnh (Context)**: Các tài liệu kiến trúc trước đây đã đề xuất mô hình phân tách hàm Request/Worker Lambda với cơ chế đệm SQS cho việc phát hiện bất thường của AI Engine, đồng thời gợi ý sử dụng các hàm backend API Gateway riêng biệt cho các tương tác trên dashboard. Hệ thống yêu cầu sự nhất quán về mặt kiến trúc, đơn giản hóa quy trình triển khai và phân định rõ ràng trách nhiệm giữa đội ngũ nền tảng CDO và đội ngũ mô hình AIOps.
- **Quyết định (Decision)**: Nhất quán hóa việc tích hợp nền tảng CDO để hướng tới một hình ảnh ECR duy nhất do AIOps cung cấp được triển khai dưới dạng một hàm Lambda container của AWS. Môi trường chạy duy nhất này sẽ phục vụ tất cả các hoạt động hợp đồng logic (`/v1/detect`, `/v1/decide`, `/v1/verify`, `/v1/status/{id}`, `/v1/audit/{audit_id}/rollback`, và `/health`). CDO quản lý nền tảng hosting (mạng VPC, ghim mã băm hình ảnh ECR digest, vai trò thực thi IAM, giới hạn reserved concurrency, và giám sát), trong khi AIOps sở hữu logic bên trong container (mô hình, logic API, điểm số tin cậy và các văn bản giải thích). SQS và DLQ hoàn toàn bị loại bỏ khỏi vòng lặp thực thi của AI Engine và chỉ được sử dụng làm vùng đệm retry cho alert routing. Để hỗ trợ các hành động tương tác trên dashboard, hàm Lambda của AI Engine được công khai qua một AWS Lambda Function URL bảo mật được ánh xạ đằng sau phân phối CloudFront duy nhất dưới dạng hành vi dẫn đường `/v1/*`. Tất cả các hàm Lambda khác do CDO sở hữu (Lambda Thu nhận, Lambda Trạng thái, và Lambda Ngăn chặn) đều hoàn toàn là các tài nguyên hỗ trợ nội bộ được gọi bởi Step Functions và không có endpoint công khai hoặc Function URL riêng biệt.
- **Hệ quả (Consequence)**:
  - Pro: Loại bỏ độ phức tạp khi triển khai và các vấn đề đồng bộ hóa runtime của việc duy trì nhiều định nghĩa và cấu hình hàm container.
  - Pro: Phân định rõ ràng trách nhiệm: CDO sở hữu hạ tầng hosting, bảo mật, mạng VPC và chính sách thực thi; AIOps sở hữu mã nguồn mô hình, logic API và kết quả phát hiện.
  - Pro: Loại bỏ độ trễ của hàng đợi SQS và độ phức tạp của dead-letter queue khỏi đường dẫn tới hạn của việc phát hiện bất thường chi phí.
  - Trade-off: Vai trò thực thi Lambda duy nhất phải được cấp quyền đọc dữ liệu S3 đã được chuẩn hóa và cache các dị thường trong DynamoDB, đòi hỏi các giới hạn tài nguyên nghiêm ngặt.
- **Các phương án thay thế đã xem xét (Alternatives considered)**:
  - Giữ nguyên các cấu hình container Request và Worker Lambda riêng biệt: Bị từ chối vì việc duy trì hai triển khai Lambda cho cùng một image mô hình sẽ tạo ra các định nghĩa tài nguyên Terraform dư thừa, gây ra hai lần Cold Start và yêu cầu mã polling bất đồng bộ phức tạp.
  - Triển khai một Private REST API Gateway facade: Bị từ chối đối với luồng batch theo lịch trình để giảm thiểu chi phí hạ tầng, do Step Functions có thể gọi trực tiếp hàm Lambda container một cách an toàn và bảo mật.