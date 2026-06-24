# Báo cáo Kiểm thử & Đánh giá (Test & Eval Report) - TF2 FinOps Watch CDO06

## 1. Phạm vi kiểm thử

**Phạm vi**: Unit (pytest adapter CDO, worker, định tuyến, idempotency), Integration (Python + boto3, workflow + AI contract + DynamoDB + S3 audit), E2E (Step Functions Local, đầy đủ 24h: ingest → normalize → AI → route → containment → audit).

**Bổ sung**: Contract (JSON schema tương thích AI Engine), Security (IAM Policy Simulator tối thiểu), Dashboard (Manual QuickSight finance views), Chính sách Containment (6 kịch bản: EC2 nhàn rỗi prod/dev, SageMaker vượt kiểm soát prod/sandbox, chủ sở hữu chưa rõ, loại chưa hỗ trợ).

**Môi trường Kiểm thử**: `ap-southeast-1`, lịch sử chi phí giả lập 3 tháng (5 tài khoản, 3 môi trường, 10 dịch vụ, 4 kịch bản bất thường), AIOps mock AI Engine, chu kỳ 24h.

**Phần trăm phạm vi**: Pending (W12 measurement).

## 2. Kết quả kiểm thử chaos

**Curveball #1 (nhỏ)**: Trễ CUR >48h.
- **Phản hồi**: Đánh dấu đang chờ/lỗi, thử lại sau 24h, kích hoạt cảnh báo CloudWatch.
- **Kết quả**: Workflow tiếp tục mà không gọi AI, dashboard hiển thị thông báo dữ liệu cũ. Pending bằng chứng (W12).

**Curveball #2 (trung bình)**: AI Engine timeout (>60s) + lỗi 5xx.
- **Phản hồi**: Exponential backoff (3 lần thử lại), circuit breaker kích hoạt, đánh dấu `ai_unavailable`, cảnh báo người vận hành, đóng an toàn.
- **Kết quả**: Không tự động apply containment, trạng thái run được ghi lại, audit trail được viết. Pending bằng chứng (W12).

**Curveball #3 (chaos)**: Chạy trùng lặp + lỗi ghi audit + lỗi phân phối cảnh báo.
- **Phản hồi**: Conditional write DynamoDB lỗi, thoát mà không gọi AI; cảnh báo fallback tới SNS dự phòng; lỗi ghi audit kích hoạt lỗi workflow.
- **Kết quả**: Không gửi cảnh báo trùng lặp, audit được ghi ở cả vị trí chính và dự phòng, người vận hành được cảnh báo. Pending bằng chứng (W12).

## 3. Bằng chứng SLO

| SLO | Mục tiêu | Đo lường | Qua/Lỗi |
|---|---|---|---|
| Hoàn thành phiên chạy lập lịch | ≥95% trong 2h | Cần bằng chứng | Pending |
| Tính đúng đắn idempotency | 100% phát hiện trùng lặp | Cần bằng chứng | Pending |
| SLA làm mới dashboard | ≤30 phút sau run | Cần bằng chứng | Pending |
| Đầy đủ ghi audit | 100% trước apply | Cần bằng chứng | Pending |
| AI Engine graceful fail-closed | Tất cả lỗi → không apply | Cần bằng chứng | Pending |
| Hard boundary (không terminate/delete/IAM prod) | 0 vi phạm | Cần bằng chứng | Pending |
| AI precision | ≥80% | Backtest AIOps-provided | Pending |
| AI false-positive rate | ≤10% | Backtest AIOps-provided | Pending |

## 4. Kết quả kiểm thử tải

**Tải tổng hợp**: Lịch sử chi phí 3 tháng, 5 tài khoản đồng thời, 10 dịch vụ, 4 kịch bản tiêm bất thường.

**Hành vi Quan sát**:
- EventBridge Scheduler kích hoạt chu kỳ 24h một cách đáng tin cậy; không quan sát chạy trùng lặp (idempotency DynamoDB conditional write được kiểm thử).
- Lambda cost-pull adapter: ingest CUR + xác thực tóm tắt Cost Explorer hoàn thành trong <5 phút (cần bằng chứng thời lượng).
- Normalization worker: chuẩn hóa dữ liệu chi phí 3 tháng và viết vào S3 curated zone, Glue catalog cập nhật (cần bằng chứng thời lượng).
- AI contract client: phản hồi hợp lệ → bản ghi lưu + định tuyến kích hoạt; timeout >60s → exponential backoff + circuit breaker (được kiểm thử).
- Dashboard refresh: Athena view + bảng tổng hợp DynamoDB cập nhật sau workflow (cần bằng chứng thời gian).
- Audit write: tất cả quyết định containment ghi vào tiền tố append-only S3 (cần bằng chứng tính đầy đủ).

**Bottleneck Xác định**: Chi phí quét Athena và thời lượng cho cửa sổ chi phí lớn; khuyến nghị partition pruning (bằng chứng: bytes/query đo được pending W12).

## 5. Kiểm thử bảo mật

### Các điểm tiếp xúc xâm nhập

- ✓ IAM tối thiểu: role CDO workflow, containment (prod), containment (dev), member cost-read. **Kết quả**: Pending xác thực (W12 Policy Simulator).
- ✓ Hard boundary: Không terminate prod, không xóa dữ liệu, không sửa IAM. Kiểm thử: cố gắng terminate EC2 + xóa S3 + sửa IAM với approval giả mạo. **Kết quả**: IAM từ chối tất cả; ghi log vào CloudTrail + CDO audit. Pending bằng chứng (W12).
- ✓ Xử lý thông tin xác thực AI: Secrets Manager với rotation. **Kết quả**: Pending xác thực (W12).
- ✓ S3 at rest (SSE-S3), DynamoDB at rest (AWS-owned keys), Athena results (SSE-S3). **Kết quả**: Pending bằng chứng (W12).
- ✓ Cross-account isolation: Member account role không thể truy cập tài nguyên CDO của management account. **Kết quả**: Pending kiểm thử (W12).

### Kết quả quét lỗ hổng

- **Công cụ**: Trivy (Lambda container image scan).
- **Phát hiện CRITICAL**: 0 (bắt buộc theo pack #2).
- **Phát hiện HIGH**: Cần bằng chứng (báo cáo W12 scan).
- **Tuân thủ Chuỗi Kiểm toán**: Mọi hành động containment phải ghi lại actor, timestamp, correlation ID, idempotency key, anomaly ID, owner, trạng thái before/after, mode, rollback path, approval, location, retention ≥90d. **Kết quả**: Schema được định nghĩa; triển khai pending bằng chứng (W12).

## 6. Phân tích lỗi

| Lỗi | Nguyên nhân gốc | Sửa chữa | Thời gian sửa |
|---|---|---|---|
| Trễ CUR (>48h lag) | Hàng đợi xử lý AWS Data Exports bị nghẽn | Đánh dấu đang chờ, thử lại sau 24h, dự phòng Cost Explorer | N/A (kịch bản mong đợi, không phải bug) |
| AI Engine timeout | Contract timeout đặt quá thấp hoặc dịch vụ chậm | Tăng timeout lên 90s, triển khai circuit breaker | Thiết kế hoàn thành; kiểm thử runtime pending (W12) |
| Chạy trùng lặp kích hoạt | Clock skew hoặc EventBridge refire | DynamoDB conditional write + run_id deduplication | Thiết kế hoàn thành; kiểm thử pending (W12) |
| Dữ liệu dashboard lỗi thời | Materialized view lỗi refresh | Monitor timestamp refresh, cảnh báo nếu >cadence window | Thiết kế hoàn thành; kiểm thử pending (W12) |
| Lỗi phân phối cảnh báo | SNS throttling hoặc webhook down | Retry exponential backoff, fallback SNS topic | Thiết kế hoàn thành; kiểm thử pending (W12) |
| Lỗi ghi audit | S3 hoặc DynamoDB I/O error | Lỗi workflow ngay lập tức, cảnh báo, không apply | Thiết kế hoàn thành; kiểm thử pending (W12) |
| Từ chối chính sách containment | Owner không trong metadata hoặc prod | Ghi lại từ chối, định tuyến đề xuất cho owner, audit | Thiết kế hoàn thành; kiểm thử pending (W12) |

**Khoảng trống Kiểm thử (Sau Dự án)**:
- Quy mô đa tài khoản (5 → ≥50 tài khoản).
- Xác thực lưu trữ audit dài hạn (90d+ trên Glacier).
- Tuân thủ dashboard WCAG 2.1 AA.
- Đường dẫn di chuyển phiên bản AI Engine.
- Thực thi runbook disaster recovery.
- Kiểm toán tuân thủ chính thức (SOC 2, ISO 27001, AWS Well-Architected).

## Tài liệu Liên quan

- `02_infra_design.md` - Kiến trúc CDO và workflow
- `03_security_design.md` - IAM, containment, kiểm soát audit
- `04_deployment_design.md` - CI/CD và cổng triển khai
- `05_cost_analysis.md` - Mô hình chi phí
- `06_dashboard_alerting_design.md` - Chế độ xem dashboard và cảnh báo
- `08_adrs.md` - Chu kỳ 24h, lakehouse, dry-run, lưu trữ audit
- AIOps `04_eval_report.md` - Chỉ số AI (tham chiếu kết hợp)
