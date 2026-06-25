# Chi tiết Hợp phần AWS - FinOps Watch CDO

<!-- Source: 02_infra_design.md. Scope excludes AI Engine hosting platform. -->

> [!IMPORTANT]
> **Ranh giới Bảo mật**: Mọi thành phần hạ tầng và kiểm soát truy cập thuộc quyền sở hữu của CDO được mô tả ở đây phải tuân thủ nghiêm ngặt ranh giới cứng: **NEVER terminate prod, delete data, hoặc modify IAM**.


Tài liệu này mở rộng các hợp phần AWS được mô tả trong [`02_infra_design.md`](02_infra_design.md) thành các chi tiết về vai trò (role), mục đích (purpose), đầu vào (input) và đầu ra (output).

Phạm vi là phân hệ kiểm soát FinOps (FinOps control plane) do CDO sở hữu:

- Thu nhận (ingest) dữ liệu chi phí từ các tài khoản thành viên (member accounts) AWS.
- Chuẩn hóa và lưu trữ bằng chứng chi phí trong một lakehouse.
- Điều phối (orchestrate) lượt chạy FinOps hàng ngày.
- Gọi một AI Engine được quản lý bên ngoài thông qua ranh giới hợp đồng (contract boundary).
- Định tuyến cảnh báo đến Tài chính (Finance) và Kỹ thuật (Engineering).
- Chỉ áp dụng các chế độ ngăn chặn an toàn (safe containment modes).
- Lưu giữ bằng chứng kiểm toán (audit evidence) để xem xét và hiển thị trên dashboard.

Tài liệu này ghi chép các hợp phần thuộc sở hữu của CDO, bao gồm các hàm container Lambda, triển khai hình ảnh ECR theo digest, hàng đợi SQS, kho lưu trữ DynamoDB, vai trò thực thi Lambda và cô lập mạng được triển khai để host container AI Engine do đội ngũ AIOps cung cấp. Nó loại trừ các phần bên trong mô hình AI (model internals), logic, trọng số (weights) và tập dữ liệu huấn luyện (training datasets) thuộc sở hữu của AIOps.

## Ranh giới Phạm vi

| Khu vực | Bao gồm ở đây | Lý do |
| --- | --- | --- |
| Thu nhận chi phí (Cost ingestion) | Có | CDO sở hữu việc thu nhận CUR và Cost Explorer vào FinOps lakehouse. |
| Lưu trữ Lakehouse (Lakehouse storage) | Có | CDO sở hữu việc lưu trữ dữ liệu thô (raw), dữ liệu chuẩn hóa (curated), kết quả Athena và bằng chứng kiểm toán (audit evidence). |
| Điều phối serverless (Serverless orchestration) | Có | CDO sở hữu EventBridge Scheduler, Step Functions và các Lambda adapters. |
| Cơ sở dữ liệu trạng thái và kiểm toán | Có | CDO sở hữu tính không thay đổi khi chạy lại (idempotency), trạng thái chạy (run state), chỉ mục kiểm toán (audit index) và các bản ghi cụ thể hóa (materialization) của dashboard. |
| Dashboard Tài chính | Có | CDO sở hữu dashboard S3 + CloudFront được hỗ trợ bởi các tóm tắt Athena/DynamoDB; QuickSight là một tùy chọn BI trong tương lai. |
| Định tuyến cảnh báo | Có | CDO sở hữu việc định tuyến cảnh báo cho Tài chính và Kỹ thuật. |
| Ngăn chặn an toàn (Safe containment) | Có | CDO sở hữu các đường dẫn ngăn chặn dry-run, gắn thẻ (tag), đề xuất (suggest) và ngăn chặn không chính thức (non-prod) đã được phê duyệt. |
| Hợp đồng API AI Engine | Có | CDO gọi, xác thực và tuân thủ các hợp đồng API và telemetry được phân bản (versioned API). |
| Hạ tầng Hosting AI Engine | Có | CDO triển khai và vận hành các hàm container Lambda, hàng đợi SQS, kho lưu trữ DynamoDB, các vai trò thực thi Lambda và cấu hình bảo mật. |
| Các phần bên trong mô hình AI & tập dữ liệu | Không | AIOps sở hữu logic mô hình, huấn luyện, trọng số và tập dữ liệu backtest. |

## Tóm tắt Hợp phần

| # | Hợp phần | Dịch vụ / Bề mặt AWS | Vai trò của nền tảng |
| --- | --- | --- | --- |
| 1 | Tài khoản thành viên AWS (AWS Member Accounts) | Các tài khoản thành viên AWS Organizations | Nguồn cung cấp dữ liệu chi phí và phạm vi mục tiêu cho các hành động ngăn chặn đã được phê duyệt. |
| 2 | Các Bucket S3 Xuất CUR (CUR S3 Export Buckets) | Amazon S3 | Nguồn lưu trữ các tệp Báo cáo Chi phí và Sử dụng (Cost and Usage Report - CUR) chi tiết. |
| 3 | Các Endpoint API Cost Explorer | AWS Cost Explorer API | Nguồn cung cấp các tín hiệu chi phí hàng ngày được tổng hợp. |
| 4 | VPC của Tài khoản Quản lý CDO (CDO Management Account VPC) | Amazon VPC | Ranh giới mạng riêng tư cho việc thực thi nền tảng CDO. |
| 5 | Các VPC Endpoints | AWS PrivateLink / Gateway Endpoints | Truy cập riêng tư vào các API AWS và các kho lưu trữ dữ liệu. |
| 6 | EventBridge Scheduler | Amazon EventBridge Scheduler | Bộ kích hoạt hàng ngày cho quy trình làm việc FinOps (FinOps workflow). |
| 7 | Quy trình Step Functions (Step Functions Workflow) | AWS Step Functions Standard | Bộ điều phối chính cho việc thu nhận, xác thực, gọi hợp đồng AI, cảnh báo và ngăn chặn. |
| 8 | Lambda Thu nhận (Ingestion Lambda) | AWS Lambda | Kéo các tệp CUR và dữ liệu Cost Explorer. |
| 9 | Lambda Trạng thái (State Lambda) | AWS Lambda | Kiểm tra và cập nhật tính không thay đổi khi chạy lại (idempotency) và trạng thái lượt chạy (run state). |
| 10 | Lambda Chuẩn hóa / Xác thực (Normalization / Validation Lambda) | AWS Lambda | Chuyển đổi dữ liệu chi phí thô thành các bản ghi sẵn sàng cho hợp đồng. |
| 11 | Hàm Lambda AI Engine (AI Engine Lambda Function) | AWS Lambda | Thực thi thuật toán phát hiện bất thường chi phí đồng bộ (đại diện cho ngữ nghĩa hợp đồng POST `/v1/detect`). |
| 12 | Lambda Định tuyến Cảnh báo (Alert Routing Lambda) | AWS Lambda | Định tuyến các quyết định bất thường đến đúng đường dẫn thông báo. |
| 13 | Lambda Ngăn chặn (Containment Lambda) | AWS Lambda | Thực thi các hành động ngăn chặn dry-run, gắn thẻ (tag), đề xuất (suggest) hoặc ngăn chặn không chính thức (non-prod) đã được phê duyệt. |
| 14 | Lambda Ghi Kiểm toán (Audit Writer Lambda) | AWS Lambda | Ghi lại các bản ghi kiểm toán không thể thay đổi (immutable audit records) trước và sau các hành động chính sách. |
| 15 | Phân vùng thô S3 (S3 Raw Zone) | Amazon S3 | Lưu trữ các dữ liệu thô được kéo từ CUR và Cost Explorer không thể thay đổi. |
| 16 | Phân vùng tinh lọc S3 (S3 Curated Zone) | Amazon S3 | Lưu trữ dữ liệu chi phí đã phân vùng, được xác thực schema và tối ưu hóa truy vấn. |
| 17 | Bucket Nhật ký Kiểm toán S3 (S3 Audit Trail Bucket) | Amazon S3 với Khóa đối tượng (Object Lock) | Kho lưu trữ bằng chứng bền vững cho các bản ghi ngăn chặn và quyết định. |
| 18 | Glue Data Catalog | AWS Glue Data Catalog | Đăng ký các schema và phân vùng cho Athena. |
| 19 | Công cụ Truy vấn Athena (Athena Query Engine) | Amazon Athena | Truy vấn dữ liệu đã chuẩn hóa (curated data) và hỗ trợ các view được cụ thể hóa (materialized views). |
| 20 | Cache Trạng thái Chạy DynamoDB (DynamoDB Run State Cache) | Amazon DynamoDB | Caches dữ liệu cụ thể hóa của dashboard và các chỉ mục không có thẩm quyền. |
| 21 | Secrets Provider | AWS Secrets Manager | Lưu trữ các tham chiếu bí mật được sử dụng bởi Lambda và các tích hợp cảnh báo. |
| 22 | Các Vai trò IAM Liên tài khoản (IAM Cross-Account Roles) | AWS IAM / STS | Cho phép truy cập đọc và ngăn chặn có kiểm soát vào các tài khoản thành viên. |
| 23 | Finance Dashboard | Amazon S3 + CloudFront | Trình bày các giao diện tĩnh dựa trên web dễ đọc cho bộ phận Tài chính mà không cần SQL; QuickSight được giữ lại làm tùy chọn BI trong tương lai. |
| 24 | Các Kênh Cảnh báo (Alert Channels) | Amazon SNS, Slack API, SES | Gửi các thông báo Tài chính, Kỹ thuật, Nền tảng và Bảo mật. |
| 25 | Giám sát CloudWatch (CloudWatch Monitoring) | CloudWatch Logs, Metrics, Alarms | Quan sát các lỗi của quy trình công việc (workflow), dữ liệu cũ (stale data) và lỗi gửi thông báo. |
| 26 | Thực thi Lambda AI Engine (AI Engine Lambda Execution) | AWS Lambda | Chạy container mô hình đồng bộ để trả về các bất thường trực tiếp. |
| 27 | Kho lưu trữ ECR (ECR Repository) | Amazon ECR | Lưu trữ các hình ảnh container AI Engine của AIOps được triển khai bằng cách ghim digest (digest pinning). |
| 28 | Hàng đợi SQS/DLQ Định tuyến Cảnh báo (Alert Routing SQS/DLQ) | Amazon SQS | Bộ đệm cho các tin nhắn cảnh báo thất bại gửi đến Slack/Email để tự động thử lại và ghi nhận lỗi vào DLQ. |
| 29 | Bộ đệm Dashboard DynamoDB (DynamoDB Dashboard Cache) | Amazon DynamoDB | Caches trạng thái chạy, siêu dữ liệu bất thường và các chế độ xem truy vấn materialized được tối ưu hóa cho bảng điều khiển. |
| 30 | Dashboard Auth Gateway (Cổng xác thực Dashboard) | Amazon Cognito | Xác thực người dùng dashboard và cung cấp phân quyền dựa trên nhóm (Finance chỉ đọc so với các điều hành viên Engineering). |
| 31 | Viewer-Request Auth Gate (Cổng xác thực yêu cầu Viewer) | Lambda@Edge | Trình xử lý viewer-request kiểm tra các cookie bảo mật HTTP-only và xác thực chữ ký JWT với Cognito JWKS trước khi chuyển tiếp yêu cầu đến bucket S3 riêng tư. |

## Các Hợp phần Loại trừ

Các hợp phần sau đây được loại trừ khỏi phạm vi nền tảng CDO vì chúng thuộc sở hữu và quản lý của AIOps:

| Hợp phần loại trừ | Mô tả | Lý do loại trừ |
| --- | --- | --- |
| Các phần bên trong mô hình AI (AI Model Internals) | Các trọng số và cấu hình của Isolation Forest / Nova LLM | Thuộc sở hữu của AIOps; cung cấp cho CDO dưới dạng một artifact hình ảnh container hóa (containerized image artifact). |
| Logic Huấn luyện Mô hình (Model Training Logic) | Logic huấn luyện lại và tinh chỉnh của AI Engine | Chạy bên trong các container nhưng các thuật toán thuộc sở hữu và được quản lý bởi AIOps. |
| Tập dữ liệu Backtest (Backtest datasets) | Các tập dữ liệu đánh giá mô hình và các điểm chuẩn (benchmarks) | AIOps duy trì đường cơ sở đo lường của mô hình; CDO chỉ lưu trữ dữ liệu đo lường tích hợp ở cấp độ lượt chạy (run-level integration telemetry). |

## 1. AWS Member Accounts

### Vai trò (Role)

Các tài khoản thành viên AWS (AWS member accounts) là các tài khoản nguồn được giám sát bởi nền tảng FinOps Watch. Chúng chứa các khối lượng công việc (workloads), tài nguyên (resources), các thẻ (tags), các mẫu chi tiêu (spend patterns) và các tệp xuất chi phí (cost exports) mà CDO đánh giá.

### Mục đích (Purpose)

Chúng cung cấp ngữ cảnh vận hành thực tế cho việc phát hiện bất thường và các quyết định ngăn chặn. Nền tảng phải bảo toàn ngữ cảnh tài khoản và môi trường bởi vì cùng một sự bất thường có thể có các hành động được cho phép khác nhau ở các môi trường sandbox, staging và prod.

### Đầu vào (Input)

- AWS Account ID (ID tài khoản AWS).
- Tên định danh (alias) hoặc tên doanh nghiệp của tài khoản.
- Nhãn môi trường (environment label), chẳng hạn như sandbox, staging, prod, research, hoặc shared services.
- Bản đồ ánh xạ chủ sở hữu và đội ngũ (owner and squad mapping).
- Tên các vai trò liên tài khoản (cross-account roles) đã phê duyệt.
- ID bên ngoài (External ID) hoặc điều kiện tin cậy để giả lập vai trò (role assumption).
- Vị trí bucket xuất CUR khi tài khoản sở hữu tệp xuất của riêng nó.
- Các thẻ tài nguyên (resource tags) như `owner`, `squad`, `environment` và trung tâm chi phí (cost center).

### Đầu ra (Output)

- Các bản ghi nguồn chi phí và sử dụng (cost and usage source records).
- Ngữ cảnh sở hữu tài nguyên (resource ownership context).
- Các khóa phân vùng tài khoản (account partition keys) cho lưu trữ lakehouse.
- Siêu dữ liệu mục tiêu ngăn chặn (containment target metadata).
- Kết quả truy cập cho các hoạt động giả lập vai trò đọc hoặc ngăn chặn liên tài khoản.
- Bằng chứng kiểm toán (audit evidence) hiển thị tài khoản nào đã được đánh giá.

## 2. CUR S3 Export Buckets

### Vai trò (Role)

Các bucket xuất CUR S3 cung cấp các tệp Báo cáo Chi phí và Sử dụng (Cost and Usage Report - CUR) chi tiết của AWS từ các tài khoản thành viên hoặc từ các tệp xuất thanh toán tập trung (centralized billing exports).

### Mục đích (Purpose)

Chúng là nguồn đầu vào chi phí chi tiết nhất cho việc phân tích cấp tài nguyên (resource-level) và cấp thẻ (tag-level). Dữ liệu CUR hỗ trợ việc điều tra lịch sử, phân vùng tài khoản và là bằng chứng cấp tài chính (finance-grade evidence).

### Đầu vào (Input)

- Cấu hình xuất CUR 2.0 (CUR 2.0 export configuration).
- Tên bucket S3 và tiền tố (prefix).
- Chu kỳ thanh toán (billing period) và đường dẫn phân vùng (partition path).
- Các tệp báo cáo định dạng Parquet hoặc CSV.
- Account ID, mã sản phẩm (product code), ID tài nguyên (resource ID), chi phí chưa pha trộn (unblended cost), lượng sử dụng (usage amount) và các thẻ tài nguyên (resource tags).
- Chính sách bucket (bucket policy) cho phép vai trò thu nhận CDO đọc các tiền tố đã phê duyệt.

### Đầu ra (Output)

- Các đối tượng CUR thô (raw CUR objects) được sao chép hoặc tham chiếu bởi Lambda thu nhận.
- URI đối tượng nguồn được giữ lại làm bằng chứng.
- Các mục dòng chi phí (cost line items) được ghi vào Phân vùng thô S3 (S3 Raw Zone).
- Các tín hiệu phân vùng bị thiếu hoặc bị trễ để thử lại (retry) và cảnh báo (alerting).

## 3. Cost Explorer API Endpoints

### Vai trò (Role)

Các endpoint API Cost Explorer cung cấp dữ liệu chi phí tổng hợp thông qua các API AWS.

### Mục đích (Purpose)

Chúng bổ sung cho CUR bằng cách cung cấp các tóm tắt chi phí hàng ngày theo dịch vụ, tài khoản, vùng (region) và cấp độ thẻ (tag-level). Điều này rất hữu ích khi có độ trễ xuất CUR hoặc khi nền tảng cần một chế độ xem tổng hợp nhanh chóng.

### Đầu vào (Input)

- Linked Account ID (ID tài khoản liên kết).
- Khoảng thời gian (time period).
- Độ chi tiết (granularity), thường là hàng ngày (daily).
- Các chỉ số (metrics) chẳng hạn như chi phí chưa pha trộn (unblended cost).
- Các trường nhóm theo (group-by) như tài khoản liên kết, dịch vụ, vùng và thẻ.
- Quyền IAM chỉ đọc chẳng hạn như `ce:GetCostAndUsage`.

### Đầu ra (Output)

- Tệp JSON tóm tắt chi phí hàng ngày.
- Trạng thái chi phí ước tính hoặc chi phí cuối cùng.
- Các tín hiệu nghẽn API (API throttling signals).
- Dữ liệu Cost Explorer thô (raw dumps) trong Phân vùng thô S3 (S3 Raw Zone).
- Các dữ liệu chi phí tổng hợp đã chuẩn hóa cho bộ lưu trữ chuẩn hóa (curated storage) và payload hợp đồng AI.

## 4. CDO Management Account VPC

### Vai trò (Role)

VPC của Tài khoản Quản lý CDO là ranh giới mạng riêng tư cho nền tảng CDO.

### Mục đích (Purpose)

Nó cô lập lưu lượng mạng của Lambda, các VPC endpoints, quyền truy cập dịch vụ riêng tư và các tài nguyên của tài khoản quản lý để dữ liệu chi phí và bản ghi kiểm toán không cần phải truyền qua internet công cộng.

### Đầu vào (Input)

- VPC CIDR block.
- Các khối CIDR subnet riêng tư (private subnet CIDR blocks).
- Các vùng sẵn sàng (availability zones) tại `ap-southeast-1`.
- Chính sách định tuyến (routing) và NAT.
- Các quy tắc nhóm bảo mật (security group rules) cho Lambda và VPC endpoints.
- Danh sách VPC endpoints.

### Đầu ra (Output)

- VPC ID.
- Danh sách ID của các subnet riêng tư.
- Danh sách ID của bảng định tuyến (route table IDs).
- ID nhóm bảo mật của Lambda.
- ID nhóm bảo mật của VPC endpoint.
- Đường dẫn kết nối riêng tư tới các dịch vụ AWS.

## 5. VPC Endpoints

### Vai trò (Role)

Các VPC endpoints cung cấp quyền truy cập mạng riêng tư từ CDO VPC tới các dịch vụ AWS.

### Mục đích (Purpose)

Chúng giảm thiểu việc để lộ dữ liệu chi phí, dữ liệu kiểm toán, bí mật (secrets), nhật ký (logs), hàng đợi (queues) và các hoạt động trạng thái (state operations) ra internet công cộng.

### Đầu vào (Input)

- VPC ID và danh sách ID của subnet.
- Nhóm bảo mật của Endpoint (Endpoint security group).
- Tên dịch vụ của Endpoint (Endpoint service names) cho S3, DynamoDB, Secrets Manager, KMS, CloudWatch Logs, SNS, SQS, Step Functions, EventBridge và CloudWatch.
- Các chính sách endpoint (endpoint policies) được giới hạn phạm vi trong các buckets, bảng (tables), chủ đề (topics), hàng đợi (queues) và vai trò (roles) được phê duyệt.

### Đầu ra (Output)

- Gateway endpoint IDs cho S3 và DynamoDB.
- Interface endpoint IDs cho các cuộc gọi API AWS riêng tư.
- Độ phân giải DNS riêng tư (private DNS resolution) cho các dịch vụ AWS được hỗ trợ.
- Bằng chứng đường dẫn mạng để phục vụ đánh giá bảo mật.

## 6. EventBridge Scheduler

### Vai trò (Role)

EventBridge Scheduler kích hoạt quy trình làm việc FinOps theo một chu kỳ xác định.

### Mục đích (Purpose)

Nó khởi động đường dẫn kiểm tra chi phí hàng ngày (daily cost inspection pipeline) mà không cần chạy một bộ lập lịch luôn hoạt động (always-on scheduler) hoặc các tác vụ cron container serverless (serverless container cron workload).

### Đầu vào (Input)

- Biểu thức lịch trình (schedule expression), thường là hàng ngày (daily).
- ARN của máy trạng thái (state machine ARN) Step Functions mục tiêu.
- ARN vai trò thực thi của Scheduler (scheduler execution role ARN).
- Payload đầu vào chứa khung thời gian chạy (run window), môi trường và phạm vi tài khoản.
- Trạng thái được bật (enabled) hoặc tắt (disabled) trong quá trình triển khai.

### Đầu ra (Output)

- Lượt gọi quy trình làm việc được lên lịch (scheduled workflow invocation).
- Dấu thời gian cuộc gọi (invocation timestamp).
- Các chỉ số cuộc gọi thất bại.
- Scheduler ARN để phục vụ cho việc giám sát (observability) và bằng chứng triển khai.

## 7. Step Functions Workflow

### Vai trò (Role)

Step Functions là bộ điều phối trung tâm (central orchestrator) cho lượt chạy CDO FinOps.

### Mục đích (Purpose)

Nó sắp xếp chuỗi các bước CDO xác định (deterministic CDO steps): kiểm tra tính không thay đổi khi chạy lại (idempotency check), thu nhận (ingestion), xác thực (validation), chuẩn hóa (normalization), gọi hợp đồng AI (AI contract invocation), định tuyến cảnh báo (alert routing), quyết định chính sách ngăn chặn (containment policy decision), ghi kiểm toán (audit writing) và xử lý lỗi (failure handling).

### Đầu vào (Input)

- Payload sự kiện từ Scheduler.
- Phạm vi tài khoản và khung thời gian thanh toán (billing window).
- Các ARN hàm Lambda.
- Tên bảng DynamoDB.
- Các tham chiếu truy vấn và nhóm làm việc (workgroup) Athena.
- Phiên bản hợp đồng AI bên ngoài.
- Các chính sách thử lại (retry), chờ đợi (wait) và hết giờ (timeout).
- ARN chủ đề cảnh báo (alert topic ARNs) và các đích đến thất bại.

### Đầu ra (Output)

- Bản ghi thực thi quy trình làm việc (workflow execution record).
- Chi tiết thành công hoặc thất bại theo từng trạng thái (per-state).
- Kết quả xác thực quyết định AI.
- Quyết định nhánh cảnh báo và ngăn chặn.
- Trạng thái thất bại cho các cảnh báo CloudWatch (CloudWatch alarms).
- Các tham chiếu kiểm toán trong DynamoDB và S3.

## 8. Ingestion Lambda

### Vai trò (Role)

Lambda thu nhận kéo dữ liệu chi phí CUR theo mặc định, hoặc conditionally kéo dữ liệu Cost Explorer như là phương án fallback.

### Mục đích (Purpose)

Nó chuyển đổi các nguồn thanh toán bên ngoài và các chỉ số hiệu năng CloudWatch thành đầu vào nền tảng thô (raw platform inputs) được lưu trữ dưới lakehouse của CDO.

### Đầu vào (Input)

- Danh sách tài khoản và chi tiết giả lập vai trò (role-assumption details).
- Tên và tiền tố bucket CUR (tiêu chuẩn đặt tên bucket: `s3://tf2-cdo{NN}-telemetry-{region}/`).
- `telemetry_delay_event` (cờ boolean để kích hoạt việc kéo dữ liệu Cost Explorer daily dự phòng thay cho CUR).
- Khung thời gian truy vấn Cost Explorer.
- Các chỉ số hiệu năng CloudWatch (bao gồm cả mảng `cpu_utilization_hourly` thô mỗi 24 giờ).
- Bucket S3 và tiền tố thô (tuân thủ tiêu chuẩn đặt tên bucket).
- KMS key ARN cho quyền truy cập ghi.
- Các thiết lập thử lại (retry) và lui về (backoff).

### Đầu ra (Output)

- Tham chiếu các tệp CUR thô.
- Các tệp JSON Cost Explorer thô (được kéo làm phương án fallback nếu `telemetry_delay_event = true`).
- Mảng thô sử dụng CPU (`cpu_utilization_hourly`).
- Các thẻ trạng thái thu nhận hạ nguồn bao gồm `data_confidence` (HIGH cho CUR, LOW cho Cost Explorer fallback).
- Bằng chứng URI đối tượng nguồn.
- Trạng thái kéo dữ liệu theo từng tài khoản và khung thời gian chi phí (cost window).
- Bản ghi lỗi đối với độ trễ CUR hoặc nghẽn API Cost Explorer.

## 9. State Lambda

### Vai trò (Role)

Lambda trạng thái quản lý các khóa lượt chạy (run locks) và các quyết định không thay đổi khi chạy lại (idempotency decisions).

### Mục đích (Purpose)

Nó ngăn chặn việc chạy trùng lặp cho cùng một tài khoản và khung thời gian thanh toán, từ đó tránh việc gửi cảnh báo trùng lặp, gọi AI trùng lặp và ghi trùng lặp trên dashboard.

### Đầu vào (Input)

- `account_id` (ID tài khoản).
- Chu kỳ thanh toán (billing period).
- Ngày thực thi (execution date).
- ID lượt chạy (Run ID).
- Tên bảng trạng thái lượt chạy (run-state table) của DynamoDB.
- Thời gian sống (TTL) của khóa và chính sách chạy trùng lặp.

### Đầu ra (Output)

- Quyết định lượt chạy được chấp nhận hoặc từ chối.
- Khóa không thay đổi khi chạy lại (idempotency key), ví dụ: `account_id:billing_period:execution_date`.
- Bản ghi trạng thái lượt chạy với trạng thái `IN_PROGRESS` (Đang xử lý), `COMPLETED` (Hoàn thành), `FAILED` (Thất bại) hoặc trạng thái trùng lặp.
- Siêu dữ liệu kiểm toán cho nỗ lực chạy trùng lặp.

## 10. Normalization / Validation Lambda

### Vai trò (Role)

Lambda chuẩn hóa và xác thực chuyển đổi các đầu vào thanh toán thô thành schema CDO ổn định.

### Mục đích (Purpose)

Nó đảm bảo dữ liệu CUR và Cost Explorer có thể truy vấn được, gửi được tới hợp đồng quyết định AI và trình bày lên Tài chính với các trường nhất quán.

### Đầu vào (Input)

- Bản ghi CUR thô (raw CUR records).
- Bản ghi Cost Explorer thô (raw Cost Explorer records).
- Bản đồ ánh xạ tài khoản và chủ sở hữu (account and owner mapping).
- Các trường schema bắt buộc.
- Các quy tắc chuẩn hóa thẻ (tag normalization rules).
- Bucket S3 và tiền tố chuẩn hóa (curated prefix).

### Đầu ra (Output)

- Các bản ghi đã chuẩn hóa với các thông tin tài khoản, dịch vụ, vùng, tài nguyên, thẻ, chu kỳ chi phí, số tiền USD và cờ ước tính/cuối cùng (estimated/final flag).
- Các tệp chuẩn hóa trong kho lưu trữ được phân vùng.
- Lỗi xác thực đối với các trường bị thiếu hoặc sai định dạng.
- Cơ chế dự phòng sở hữu (ownership fallback) chẳng hạn như `unassigned-resources` (tài nguyên không được phân bổ).

## 11. Hàm Lambda AI Engine (AI Engine Lambda Function)

### Vai trò (Role)

Thực thi thuật toán phát hiện bất thường chi phí đồng bộ (đại diện cho ngữ nghĩa hợp đồng POST `/v1/detect` ở cấp độ hợp đồng).

### Mục đích (Purpose)

Đóng vai trò là điểm bắt đầu cho luồng phát hiện bất thường AI. Nó xác thực các schema yêu cầu đầu vào, kiểm tra xung đột tính không lặp lại (idempotency), và chạy mô hình phát hiện bất thường một cách đồng bộ.

### Đầu vào (Input)

- Payload khung thời gian chi phí đã chuẩn hóa (kèm cờ `telemetry_delay_event`).
- ID lượt chạy và khóa không thay đổi khi chạy lại (tiêu chuẩn đặt tên bucket: `s3://tf2-cdo{NN}-telemetry-{region}/`).
- Phạm vi tài khoản.
- Phiên bản hợp đồng.
- Các chỉ số hiệu năng CloudWatch (bao gồm cả mảng `cpu_utilization_hourly` thô mỗi 24 giờ).
- Tham chiếu bí mật để ký xác thực tính toàn vẹn payload.

### Đầu ra (Output)

- Trạng thái thành công (tương đương cấp độ hợp đồng với mã HTTP `200 OK`) chứa:
  - `success` (boolean)
  - `correlation_id` (UUID v4)
  - `anomalies_detected` (boolean)
  - `anomalies_list` (mảng các bất thường được phát hiện)
  - `data_confidence` (HIGH/LOW, chỉ ra chất lượng nguồn dữ liệu CUR so với Cost Explorer fallback)
  - `callback_url` (tùy chọn, để gửi thông báo callback bất đồng bộ bổ sung)
  - `error_message` (tùy chọn)
- Các phản hồi đầu ra Decide (đại diện cho endpoint logic `/v1/decide`):
  - `action_plan` (kế hoạch can thiệp)
  - `applied_payload` (các lệnh để thực thi)
  - `rollback_payload.boto3_equivalent` (được lưu vào DynamoDB ngay lập tức, CDO thực thi rollback từ cache thông qua Boto3, sau đó báo cáo qua `POST /v1/audit/{audit_id}/rollback`)
- Các mã lỗi hoặc lỗi xác thực (tương đương với các mã HTTP `400 Bad Request` hoặc `409 Conflict`) nếu kiểm tra idempotency hoặc xác thực payload thất bại.

## 12. Alert Routing Lambda

### Vai trò (Role)

Lambda định tuyến cảnh báo gửi các thông báo bất thường và thông báo quy trình công việc tới đúng kênh.

### Mục đích (Purpose)

Nó phân tách các cảnh báo Tài chính, Kỹ thuật, Nền tảng và Bảo mật để mỗi nhóm người dùng nhận được thông tin có thể thực thi mà không có các chi tiết nhạy cảm không cần thiết.

### Đầu vào (Input)

- Payload quyết định AI.
- Bản đồ định tuyến cảnh báo (alert route map).
- Siêu dữ liệu chủ sở hữu và đội ngũ (owner and squad metadata).
- Độ nghiêm trọng và độ tin cậy.
- Liên kết dashboard hoặc liên kết kiểm toán.
- ARN chủ đề SNS (SNS topic ARNs).
- Tham chiếu bí mật cho Slack webhook.
- Cấu hình đích đến SES.
- Chính sách ẩn thông tin nhạy cảm (redaction policy).

### Đầu ra (Output)

- Sự kiện cảnh báo Tài chính.
- Sự kiện cảnh báo Kỹ thuật.
- Sự kiện leo thang Nền tảng hoặc Bảo mật.
- Trạng thái gửi cảnh báo.
- Tin nhắn hàng đợi thư rác (DLQ message) cho việc gửi lỗi.
- Tham chiếu kiểm toán liên kết cảnh báo với lượt chạy.

## 13. Containment Lambda

### Vai trò (Role)

Lambda ngăn chặn đánh giá và thực thi các hành động ngăn chặn an toàn trong các tài khoản thành viên.

### Mục đích (Purpose)

Nó chuyển đổi các quyết định chính sách đã được phê duyệt thành các hành động có kiểm soát trong khi vẫn bảo toàn ranh giới nghiêm ngặt rằng môi trường production chỉ dừng lại ở các hành động gắn thẻ (tag), đề xuất (suggest) hoặc chạy thử (dry-run).

### Đầu vào (Input)

- Payload quyết định AI.
- Ngữ cảnh tài khoản và môi trường.
- Bản đồ chính sách ngăn chặn (containment policy map).
- Chế độ thực thi (execution mode), chẳng hạn như dry-run, tag, suggest, hoặc apply đối với môi trường non-prod đã được phê duyệt.
- ARN hoặc ID tài nguyên mục tiêu.
- Tên vai trò ngăn chặn liên tài khoản (cross-account containment role name).
- Trạng thái phê duyệt (approval status).
- Cấu hình của bộ ghi kiểm toán (audit writer configuration).

### Đầu ra (Output)

- Kết quả chạy thử (dry-run result).
- Kết quả gắn thẻ (tagging result).
- Bản ghi đề xuất (suggestion record).
- Kết quả ngăn chặn non-prod đã phê duyệt.
- Bản ghi hành động bị từ chối.
- Trạng thái trước (before state) và trạng thái sau đề xuất (proposed-after state).
- Đường dẫn khôi phục (rollback path).
- ID bản ghi kiểm toán.

## 14. Audit Writer Lambda

### Vai trò (Role)

Lambda ghi kiểm toán ghi lại quyết định và bằng chứng ngăn chặn.

### Mục đích (Purpose)

Nó tạo ra nhật ký kiểm toán có thể truy vết (traceable audit trail) bắt buộc cho việc đánh giá của Tài chính, Kỹ thuật và tuân thủ (compliance).

### Đầu vào (Input)

- ID lượt chạy (Run ID) và ID tương quan (Correlation ID).
- Khóa không thay đổi khi chạy lại (idempotency key).
- ID bất thường (Anomaly ID).
- Chủ sở hữu tài nguyên và ID tài nguyên mục tiêu.
- Trạng thái trước (before state).
- Trạng thái sau đề xuất (proposed-after state).
- Chế độ thực thi (execution mode).
- Trạng thái phê duyệt (approval status).
- Vị trí lưu giữ (retention location).
- Đường dẫn khôi phục (rollback path).

### Đầu ra (Output)

- Bản ghi chỉ mục kiểm toán trong DynamoDB.
- Đối tượng bằng chứng kiểm toán trong S3.
- Siêu dữ liệu lưu giữ (retention metadata).
- ID bản ghi kiểm toán có thể liên kết từ dashboard.
- Tín hiệu lỗi khi việc ghi kiểm toán thất bại.

## 15. S3 Raw Zone

### Vai trò (Role)

Phân vùng thô S3 lưu trữ các đầu vào chi phí ban đầu.

### Mục đích (Purpose)

Nó lưu trữ bằng chứng nguồn không thể thay đổi trước khi chuyển đổi, hỗ trợ xử lý lại (reprocessing) và đánh giá kiểm toán.

### Đầu vào (Input)

- Các tệp CUR từ tệp xuất S3 của tài khoản thành viên.
- Phản hồi JSON từ Cost Explorer.
- ID tài khoản nguồn (source account ID).
- Chu kỳ thanh toán (billing period).
- Dấu thời gian thu nhận (ingestion timestamp).
- Cấu hình mã hóa KMS.
- Tiêu chuẩn đặt tên bucket: đặt tên bucket chuẩn `s3://tf2-cdo{NN}-telemetry-{region}/raw/`.

### Đầu ra (Output)

- Các đối tượng thô được phân vùng theo tài khoản và ngày.
- URI bằng chứng nguồn.
- Đầu vào cho việc chuẩn hóa và xác thực.
- Điểm phục hồi (recovery point) khi việc xử lý dữ liệu chuẩn hóa bị lỗi.

## 16. S3 Curated Zone

### Vai trò (Role)

Phân vùng chuẩn hóa S3 lưu trữ các bản ghi chi phí đã chuẩn hóa và tối ưu hóa cho truy vấn.

### Mục đích (Purpose)

Nó cung cấp lớp lakehouse ổn định cho các truy vấn Athena, xây dựng payload hợp đồng AI và các dashboard Tài chính.

### Đầu vào (Input)

- Các bản ghi thô đã được xác thực.
- Các trường dịch vụ và tên hiển thị đã chuẩn hóa.
- Các thẻ chủ sở hữu và thẻ đội ngũ (owner and squad tags).
- Giá trị phân vùng theo tài khoản, năm và tháng.
- Đầu ra chuyển đổi Parquet (Parquet conversion output).
- Tiêu chuẩn đặt tên bucket: đặt tên bucket chuẩn `s3://tf2-cdo{NN}-telemetry-{region}/curated/`.

### Đầu ra (Output)

- Các đối tượng chuẩn hóa được phân vùng.
- Tập dữ liệu có thể đọc được bằng Athena (Athena-readable datasets).
- Đầu vào truy vấn cho các view cụ thể hóa của dashboard.
- Đầu vào khung thời gian bằng chứng cho các bản ghi quyết định AI.

## 17. S3 Audit Trail Bucket

### Vai trò (Role)

Bucket nhật ký kiểm toán S3 lưu trữ các bằng chứng lưu giữ lâu dài cho các bản ghi ngăn chặn và quyết định.

### Mục đích (Purpose)

Nó đóng vai trò là kho lưu trữ bằng chứng bền vững để truy vết, đặc biệt là khi DynamoDB chỉ chứa các chỉ mục (indexes) hoặc các bản ghi cụ thể hóa hiển thị trên dashboard.

### Đầu vào (Input)

- Đầu ra của bộ ghi kiểm toán (audit writer output).
- Các bản ghi đề xuất và kết quả ngăn chặn.
- Các tham chiếu bằng chứng quyết định AI.
- Thời gian lưu giữ (retention period), tối thiểu 90 ngày.
- Thiết lập Khóa đối tượng (Object Lock) khi được kích hoạt.
- Tiêu chuẩn đặt tên bucket: đặt tên bucket chuẩn `s3://tf2-cdo{NN}-telemetry-{region}/audit/` và `s3://tf2-cdo{NN}-telemetry-{region}/idempotency/`.

### Đầu ra (Output)

- Các đối tượng kiểm toán chỉ được thêm (append-only audit objects).
- URI bằng chứng được liên kết từ DynamoDB và dashboard S3 + CloudFront.
- Bằng chứng lưu giữ để đánh giá.
- Bằng chứng phục hồi cho việc điều tra sự cố.

## 18. Glue Data Catalog

### Vai trò (Role)

Glue Data Catalog lưu trữ siêu dữ liệu (metadata) của cơ sở dữ liệu và bảng cho lakehouse.

### Mục đích (Purpose)

Nó giúp dữ liệu thô và dữ liệu chuẩn hóa trong S3 có thể truy vấn được bởi Athena mà không cần di chuyển dữ liệu vào một kho dữ liệu cố định (fixed data warehouse).

### Đầu vào (Input)

- Các vị trí lưu trữ S3 thô (raw) và chuẩn hóa (curated).
- Schema của các bảng.
- Các khóa phân vùng (partition keys) như `account_id`, `year` và `month`.
- Cấu hình bảng IaC và các tham số partition projection (ADR-014).
- Các định nghĩa kiểu dữ liệu.

### Đầu ra (Output)

- Cơ sở dữ liệu Glue (Glue database).
- Các bảng Glue (Glue tables).
- Siêu dữ liệu phân vùng.
- Trình đăng ký schema (schema registry) cho các truy vấn Athena.
- Bằng chứng danh mục (catalog evidence) cho dashboard và các quy trình công việc truy vấn.

## 19. Athena Query Engine

### Vai trò (Role)

Athena thực thi các truy vấn SQL serverless trên dữ liệu S3 lakehouse.

### Mục đích (Purpose)

Nó vận hành các view chi phí được cụ thể hóa, các tập dữ liệu dashboard, các truy vấn bằng chứng bất thường và các quy trình công việc điều tra mà không yêu cầu người dùng Tài chính phải trực tiếp viết SQL.

### Đầu vào (Input)

- Tên cơ sở dữ liệu và bảng của Glue.
- Các phân vùng S3 chuẩn hóa.
- Nhóm làm việc Athena (Athena workgroup).
- Giới hạn kích thước byte truy vấn (query byte cutoff).
- Bucket lưu trữ kết quả truy vấn.
- Các định nghĩa truy vấn được đặt tên hoặc mã SQL view của dashboard.

### Đầu ra (Output)

- Kết quả truy vấn trong S3.
- Đầu vào dashboard đã được cụ thể hóa.
- Khung thời gian bằng chứng cho các quyết định bất thường.
- Tín hiệu dữ liệu cũ (stale-data signal) khi phân vùng chuẩn hóa mới nhất đã quá hạn.
- Các chỉ số chi phí truy vấn.

## 20. DynamoDB Run State and Audit

### Vai trò (Role)

DynamoDB lưu trữ trạng thái vận hành, bản ghi không thay đổi khi chạy lại (idempotency), chỉ mục kiểm toán (audit indexes) và các bản ghi cụ thể hóa hiển thị trên dashboard.

### Mục đích (Purpose)

Nó cung cấp các kiểm tra trạng thái với độ trễ thấp cho quy trình công việc và tra cứu nhanh cho các dashboard và cảnh báo.

### Đầu vào (Input)

- ID lượt chạy (Run ID).
- Khóa không thay đổi khi chạy lại (idempotency key).
- Tài khoản và khung thời gian thanh toán (billing window).
- Trạng thái lượt chạy (state status).
- ID bản ghi kiểm toán.
- Các trường cụ thể hóa của dashboard.
- Thời gian sống (TTL) và chính sách lưu giữ.

### Đầu ra (Output)

- Kết quả khóa lượt chạy (run lock result).
- Bản ghi trạng thái lượt chạy.
- Phát hiện chạy trùng lặp (duplicate-run detection).
- Bản ghi chỉ mục kiểm toán.
- Bản ghi tóm tắt dashboard.
- Trạng thái thất bại cho các cảnh báo và chạy lại (redrive).

## 21. Secrets Provider

### Vai trò (Role)

Secrets Manager lưu trữ các khối thông tin bí mật (secret containers) và các tham chiếu bí mật được yêu cầu bởi các hợp phần thực thi của CDO.

### Mục đích (Purpose)

Nó giữ các giá trị nhạy cảm nằm ngoài các biến Terraform, tài liệu, văn bản thuần (plaintext) của môi trường Lambda và payload cảnh báo.

### Đầu vào (Input)

- Tên bí mật cho cấu hình endpoint AI.
- Tên bí mật của khóa ký hợp đồng.
- Tên bí mật của Slack webhook.
- Tên bí mật của thông tin xác thực dashboard nếu cần.
- Tên bí mật của External ID seed.
- KMS key để mã hóa bí mật.
- Chính sách xoay vòng (rotation policy).

### Đầu ra (Output)

- Các ARN bí mật được truyền vào các chính sách Lambda và IAM.
- Siêu dữ liệu xoay vòng bí mật.
- Kiểm toán truy cập thông qua CloudTrail.
- Đường dẫn truy xuất bí mật trong thời gian chạy cho các vai trò thực thi đã phê duyệt.

## 22. IAM Cross-Account Roles

### Vai trò (Role)

Các vai trò IAM và giả lập vai trò STS (STS role assumption) cung cấp quyền truy cập có kiểm soát từ tài khoản quản lý CDO vào các tài khoản thành viên.

### Mục đích (Purpose)

Chúng cho phép CDO đọc dữ liệu chi phí và thực thi các ngăn chặn an toàn mà không cần các đặc quyền tài khoản quá rộng.

### Đầu vào (Input)

- ARN vai trò tài khoản quản lý (management account role ARN).
- Danh sách ID tài khoản thành viên.
- ID bên ngoài (External ID).
- Điều kiện tài khoản nguồn (source account condition).
- Các yêu cầu về thẻ phiên làm việc (session tags).
- Quyền chỉ đọc CUR và Cost Explorer.
- Quyền ngăn chặn được giới hạn phạm vi theo môi trường và loại hành động.

### Đầu ra (Output)

- Phiên giả lập vai trò (assumed-role session) cho việc thu nhận.
- Phiên giả lập vai trò cho việc ngăn chặn.
- Tín hiệu truy cập bị từ chối khi các điều kiện chính sách thất bại.
- Các sự kiện kiểm toán CloudTrail.
- Các thẻ phiên làm việc (session tags) liên kết các hành động với các ID lượt chạy CDO.

## 23. Finance Dashboard

### Vai trò (Role)

Một dashboard web nội bộ nhẹ nhàng được lưu trữ dưới dạng các static assets trong Amazon S3 và phân phối qua Amazon CloudFront. Giao diện này đọc các tóm tắt đã được tính toán trước, dễ đọc cho bộ phận tài chính từ các đối tượng JSON trên S3 hoặc các bản ghi DynamoDB. Step Functions thực hiện các tiến trình tính toán và cập nhật DynamoDB; người dùng Tài chính không bao giờ phải viết SQL.

QuickSight được giữ lại làm tùy chọn BI trong tương lai cho các đội ngũ Tài chính lớn hơn hoặc cho báo cáo cấp quản lý, nhưng đây không phải là dashboard MVP mặc định vì dự án capstone ưu tiên chi phí định kỳ thấp và không mất phí bản quyền BI cho mỗi người đọc.

### Mục đích (Purpose)

Nó trả lời các câu hỏi hướng tới Giám đốc Tài chính (CFO) mà không cần SQL: điều gì đã thay đổi, ai sở hữu nó, độ tin cậy của nền tảng là bao nhiêu, và hành động nào được phép thực hiện.

### Đầu vào (Input)

- Các tóm tắt tính toán trước dạng JSON trên S3.
- Các bản ghi lượt chạy được cụ thể hóa trong DynamoDB.
- Các liên kết bản ghi kiểm toán.
- Siêu dữ liệu chủ sở hữu và đội ngũ (owner and squad metadata).
- Các trường độ nghiêm trọng và độ tin cậy.
- Danh sách người dùng được ủy quyền trên CloudFront hoặc các nhóm Cognito.
- Các tập dữ liệu Athena (thông qua xuất thủ công hoặc tích hợp QuickSight BI trong tương lai).

### Đầu ra (Output)

- Giao diện dashboard Tài chính.
- Trạng thái làm mới (refresh status) của tệp/tập dữ liệu JSON trên S3.
- Các tóm tắt bất thường về chi tiêu (spend anomaly summaries).
- Phân tích chi tiết theo chủ sở hữu và định tuyến.
- Các liên kết kiểm toán cho các quyết định ngăn chặn.
- Tín hiệu dữ liệu dashboard bị cũ khi các đầu vào bị trễ.

## 24. Alert Channels

### Vai trò (Role)

Các kênh cảnh báo gửi các kết quả phát hiện của nền tảng và các tín hiệu lỗi tới đúng nhóm người nhận.

### Mục đích (Purpose)

Chúng đảm bảo Tài chính, Kỹ thuật, Nền tảng và Bảo mật nhận được các thông báo được định tuyến, ẩn các thông tin nhạy cảm (redacted) và có thể thực thi.

### Đầu vào (Input)

- Quyết định định tuyến cảnh báo.
- ARN chủ đề SNS (SNS topic ARNs).
- Tham chiếu Slack webhook.
- Đích đến email SES.
- Độ nghiêm trọng và độ tin cậy.
- Chủ sở hữu và định tuyến đội ngũ.
- Liên kết dashboard hoặc kiểm toán.
- Chính sách ẩn thông tin nhạy cảm.

### Đầu ra (Output)

- Cảnh báo Tài chính.
- Cảnh báo Kỹ thuật.
- Leo thang Nền tảng hoặc Bảo mật.
- Thông báo dự phòng qua email.
- Tin nhắn DLQ của cảnh báo bị lỗi.
- Các chỉ số gửi thông báo để phục vụ giám sát.

## 25. CloudWatch Monitoring

### Vai trò (Role)

CloudWatch ghi lại nhật ký (logs), các chỉ số (metrics) và cảnh báo (alarms) cho phân hệ kiểm soát serverless (serverless control plane).

### Mục đích (Purpose)

Nó cung cấp khả năng phát hiện vận hành cho các quy trình công việc bị lỗi, dữ liệu dashboard cũ, lỗi Lambda, lỗi gửi cảnh báo và lỗi ghi kiểm toán.

### Đầu vào (Input)

- Các nhóm nhật ký Lambda (Lambda log groups).
- Các chỉ số thực thi Step Functions.
- Các chỉ số EventBridge Scheduler.
- Các chỉ số nghẽn DynamoDB (DynamoDB throttling metrics).
- Tín hiệu phân vùng bị lỗi hoặc bị cũ của Athena.
- Trạng thái gửi cảnh báo.
- Chỉ số độ tươi mới (freshness metric) của dashboard.

### Đầu ra (Output)

- Nhật ký CloudWatch (CloudWatch logs).
- Chỉ số CloudWatch (CloudWatch metrics).
- Cảnh báo CloudWatch (CloudWatch alarms).
- Cảnh báo cho kỹ sư vận hành (operator alerts).
- Bằng chứng cho thấy nền tảng đã chạy, bị lỗi, thử lại hoặc đã phục hồi.

## 26. Thực thi Lambda AI Engine (AI Engine Lambda Execution)

### Vai trò (Role)

Chạy container mô hình AI và ghi kết quả vào S3.

### Mục đích (Purpose)

Thực hiện suy luận mô hình và phân tích bất thường bên trong một hàm Lambda được khởi tạo từ hình ảnh container do AIOps cung cấp. Nó chạy đồng bộ trong chu kỳ phát hiện trực tiếp, và sử dụng mức concurrency dành riêng để kiểm soát vùng ảnh hưởng (blast radius) và các giới hạn nghẽn (throttle limits).

### Đầu vào (Input)

- Dữ liệu chi phí thô và các chỉ số sử dụng CloudWatch từ S3 (bao gồm mảng `cpu_utilization_hourly` và cờ `telemetry_delay_event`; tiêu chuẩn đặt tên bucket: `s3://tf2-cdo{NN}-telemetry-{region}/`).
- Hash hình ảnh ECR không thể thay đổi (digest pinning).
- ARN của bucket S3 chứa bằng chứng.
- ARN vai trò thực thi Lambda.
- Cấu hình mức concurrency dành riêng (reserved concurrency).

### Đầu ra (Output)

- Kết quả phát hiện bất thường (bao gồm `data_confidence` và `callback_url` tùy chọn) và giải thích được trả về đồng bộ cho bộ điều phối Step Functions.
- Quyết định và hành động khuyến nghị bao gồm `rollback_payload.boto3_equivalent` được CDO cache trong DynamoDB (rollback được thực thi bởi CDO từ cache, sau đó báo cáo qua `POST /v1/audit/{audit_id}/rollback`).
- Bằng chứng lập luận chi tiết được ghi vào bucket S3.
- Các vết thực thi (traces) gửi tới X-Ray và nhật ký (logs) gửi tới CloudWatch.

## 27. Kho lưu trữ ECR (ECR Repository)

### Vai trò (Role)

Lưu trữ các hình ảnh container AI Engine của AIOps được gắn thẻ phiên bản.

### Mục đích (Purpose)

Hoạt động như một kho lưu trữ duy nhất để triển khai. Hình ảnh được ghim bằng mã băm SHA256 (digest pinning) trong cấu hình Lambda.

### Đầu vào (Input)

- Hình ảnh được build từ quy trình CI/CD.
- Quét lỗi bảo mật CVE và các thẻ xác thực tuân thủ.

### Đầu ra (Output)

- URI hình ảnh đã ghim (`.dkr.ecr.ap-southeast-1.amazonaws.com/ai-engine@sha256:...`) được kéo bởi AWS Lambda.

## 28. Hàng đợi SQS/DLQ Định tuyến Cảnh báo (Alert Routing SQS/DLQ)

### Vai trò (Role)

Bộ đệm cho các tin nhắn cảnh báo thất bại gửi đến Slack/Email để tự động thử lại.

### Mục đích (Purpose)

Tách rời việc phân phối thông báo cảnh báo khỏi quá trình thực thi workflow chính. Thiết kế này giúp ngăn ngừa các lỗi kết nối tạm thời đến Slack/Email API làm gián đoạn pipeline CDO, tự động thử lại việc phân phối tin nhắn và định tuyến các lỗi kéo dài đến DLQ.

### Đầu vào (Input)

- Payload JSON cảnh báo cho Slack/Email.
- Cấu hình Hàng đợi thư rác (Dead Letter Queue).

### Đầu ra (Output)

- Các cảnh báo được gửi lại thành công đến các mục tiêu Slack/Email.
- Tin nhắn DLQ khi việc phân phối thất bại hoàn toàn.

## 29. Bộ đệm Dashboard DynamoDB (DynamoDB Dashboard Cache)

### Vai trò (Role)

Kho lưu trữ bộ đệm đọc cho trạng thái chạy, các dị thường và nhật ký kiểm toán.

### Mục đích (Purpose)

Cung cấp các giao diện đọc độ trễ thấp để hỗ trợ Dashboard S3 + CloudFront, cache các tóm tắt lượt chạy và trạng thái can thiệp mà không cần truy vấn trực tiếp lớp Athena/S3 có thẩm quyền.

### Đầu vào (Input)

- Các materialized view được ghi bởi các Lambda của nền tảng CDO sau mỗi lượt chạy.

### Đầu ra (Output)

- Trạng thái và kết quả với độ trễ thấp được truy xuất nhanh chóng bởi dashboard S3 + CloudFront.

## 31. Amazon Cognito

### Vai trò (Role)

Xác thực người dùng và cung cấp thư mục người dùng.

### Mục đích (Purpose)

Xác thực người dùng dashboard thông qua Cognito Hosted UI an toàn (Luồng mã cấp quyền với PKCE - Authorization Code Flow with PKCE) và xác định các nhóm người dùng (`finops-finance-readonly`, `finops-engineering-operator`, `finops-cdo-admin`) để ủy quyền cho các thao tác trên dashboard.

### Đầu vào (Input)

- Thông tin đăng nhập tương tác của người dùng được nhập trong Cognito Hosted UI.

### Đầu ra (Output)

- Các mã JWT ID, Access, và Refresh chứa thông tin xác nhận nhóm (group claims), được lưu trữ dưới dạng cookie bảo mật.

## 32. Lambda@Edge Viewer Request Auth

### Vai trò (Role)

Bộ lọc ủy quyền ở cấp độ Edge (Edge-level authorization filter).

### Mục đích (Purpose)

Chặn các yêu cầu dashboard tại sự kiện viewer request của CloudFront, phân tích cú pháp các cookie JWT, kiểm tra chữ ký với Cognito JWKS, và xác minh thời gian hết hạn của phiên làm việc. Từ chối truy cập hoặc chuyển hướng đăng nhập nếu phiên làm việc không hợp lệ.

### Đầu vào (Input)

- Các cookie và tiêu đề viewer request gửi đến.

### Đầu ra (Output)

- Chuyển tiếp yêu cầu đến origin S3 riêng tư với xác thực OAC (nếu được ủy quyền) hoặc chuyển hướng 302 đến Cognito Hosted UI.

## Luồng Dữ liệu ở Cấp độ Hợp đồng (Contract-Level Data Flows)

### Hợp đồng Kéo Dữ liệu Chi phí (Cost Data Pull Contract)

| Trường | Chi tiết |
| --- | --- |
| Các hợp phần chịu trách nhiệm | EventBridge Scheduler, Step Functions, Lambda Thu nhận, Phân vùng thô S3, Phân vùng chuẩn hóa S3, Glue, Athena |
| Đầu vào | Phạm vi tài khoản, khung thời gian chi phí, vị trí S3 của CUR, các tham số truy vấn Cost Explorer |
| Đầu ra | URI đối tượng nguồn, khung thời gian chi phí, tài khoản, dịch vụ, vùng, tài nguyên, chủ sở hữu thẻ (tag owner), chi phí chưa pha trộn, cờ ước tính/cuối cùng |
| Hành vi lỗi | Thử lại khi có độ trễ CUR và nghẽn API Cost Explorer; cảnh báo nếu độ trễ vượt quá ngưỡng được cấu hình |

### Hợp đồng Quyết định AI bên ngoài (External AI Decision Contract)

| Trường | Chi tiết |
| --- | --- |
| Các hợp phần CDO chịu trách nhiệm | Step Functions, Hàm Lambda AI Engine, DynamoDB, nhật ký kiểm toán S3, SQS |
| Các hợp phần loại trừ | Trọng số mô hình AI Engine, các tác vụ huấn luyện AI, tập dữ liệu huấn luyện mô hình, và logic bên trong mô hình AI |
| Đầu vào | Khung thời gian chi phí đã chuẩn hóa, ID lượt chạy (run ID), phạm vi tài khoản, phiên bản hợp đồng, khung thời gian bằng chứng (evidence window) |
| Đầu ra | Phiên bản mô hình, ID bất thường, độ tin cậy, độ nghiêm trọng, chi tiêu kỳ vọng, chi tiêu thực tế, chênh lệch (delta), giải thích, định tuyến được đề xuất, chế độ ngăn chặn được đề xuất, URI bằng chứng |
| Hành vi lỗi | Đóng lỗi an toàn (fail closed), chặn ngăn chặn, cảnh báo cho kỹ sư vận hành và ghi lại trạng thái hợp đồng bị lỗi vào DynamoDB |

### Hợp đồng Cảnh báo và Ngăn chặn (Alert And Containment Contract)

| Trường | Chi tiết |
| --- | --- |
| Các hợp phần chịu trách nhiệm | Lambda Định tuyến Cảnh báo, Lambda Ngăn chặn, DynamoDB, nhật ký kiểm toán S3, SNS, Slack, SES, dashboard S3 + CloudFront |
| Đầu vào | Quyết định AI đã được xác thực, định tuyến chủ sở hữu, môi trường, siêu dữ liệu tài nguyên, chính sách ngăn chặn, chế độ thực thi |
| Đầu ra | Mục tiêu định tuyến, yêu cầu phê duyệt, chế độ thực thi, trạng thái trước/sau, đường dẫn khôi phục, ID bản ghi kiểm toán |
| Hành vi lỗi | Ghi lại bản ghi kiểm toán bị từ chối hoặc bị lỗi, định tuyến cảnh báo nghiêm trọng, không thử lại các hành động ngăn chặn không an toàn |

## Quy tắc An toàn Môi trường Production (Production Safety Rules)

- Ngăn chặn trên môi trường Production chỉ giới hạn ở việc gắn thẻ (tag), đề xuất (suggest) hoặc chạy thử (dry-run).
- Không chấm dứt (terminate) các tài nguyên production.
- Không xóa dữ liệu.
- Không sửa đổi IAM từ các quy trình ngăn chặn.
- Ghi lại bằng chứng kiểm toán trước khi thực hiện bất kỳ hành động ở chế độ áp dụng thực tế (apply-mode) nào trên môi trường non-prod.
- Các thẻ chủ sở hữu bị thiếu (missing owner tags) phải được duy trì hiển thị và định tuyến tới kênh hạ tầng CDO.
- Các sự kiện demo giả lập (synthetic demo events) phải được gắn nhãn là `synthetic-demo` and không được coi là bằng chứng huấn luyện mô hình của AIOps.

## Khả năng Truy vết Nguồn (Source Traceability)

| Phần nguồn trong `02_infra_design.md` | Các hợp phần được ghi lại ở đây |
| --- | --- |
| `1. Architecture diagram` | Các tài khoản thành viên, CUR, Cost Explorer, EventBridge, Step Functions, Lambda, S3, Glue, Athena, DynamoDB, Slack, SES, dashboard S3 + CloudFront |
| `1.1 High-Level Architecture Overview` | Bộ điều phối, lakehouse, động cơ cảnh báo/ngăn chặn, dashboard/các kênh |
| `1.2 Ingestion & Data Lakehouse Workflow` | CUR, Cost Explorer, Scheduler, Step Functions, Lambda Thu nhận, S3 Raw, S3 Curated, Glue, Athena |
| `1.4 Alerting & Containment Engine` | Lambda Cảnh báo, Lambda Ngăn chặn, Lambda Trạng thái, DynamoDB trạng thái/kiểm toán, tài nguyên thành viên, Slack, SES, dashboard S3 + CloudFront |
| `2. Component table` | EventBridge Scheduler, Step Functions, Lambda, S3, Glue, Athena, DynamoDB, Secrets Manager, dashboard S3 + CloudFront, SNS/Slack, nhân tố Ngăn chặn (Containment Worker), các hàm container Lambda, ECR, SQS |
| `4. Multi-account approach` | Các tài khoản thành viên, vai trò liên tài khoản kéo CUR, vai trò liên tài khoản ngăn chặn, quy trình onboarding tài khoản, tính không thay đổi khi chạy lại (idempotency) |
| `6. Scaling strategy` | Phân vùng Athena, tự động co giãn theo yêu cầu (on-demand scaling) của DynamoDB, tự động co giãn concurrency dành riêng của Lambda (Lambda reserved concurrency scaling) |
| `7. Failure modes + recovery` | Trễ CUR, nghẽn API Cost Explorer, lỗi quy trình làm việc (workflow failure), chạy trùng lặp, dữ liệu dashboard cũ, lỗi gửi cảnh báo, bị từ chối ngăn chặn, không khớp hợp đồng AI, khởi động lạnh Lambda và xử lý không đồng bộ |
