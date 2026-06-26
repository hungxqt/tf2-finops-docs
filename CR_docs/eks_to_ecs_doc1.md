# Architecture Review - AI Engine Hosting Platform (Document 1)

## Current Decision

Hiện tại kiến trúc CDO lựa chọn triển khai AI Engine trên Amazon EKS với Managed Node Groups (On-Demand và Spot).

Mục tiêu ban đầu:

* Host AI Engine do AIOps cung cấp.
* Hỗ trợ autoscaling.
* Tách workload giữa On-Demand và Spot.
* Chuẩn bị khả năng mở rộng cho các workload AI trong tương lai.

---

## Re-evaluation Against Current Requirements

Sau khi rà soát lại yêu cầu chính thức của Task Force 2 FinOps Watch, nhóm nhận thấy:

### Requirements thực tế

CDO chỉ cần:

* Triển khai AI Engine do AIOps cung cấp.
* Expose API nội bộ cho anomaly detection.
* Được gọi theo batch cadence 24 giờ.
* Đảm bảo availability và khả năng mở rộng cơ bản.

### Requirements không bắt buộc

Client không yêu cầu:

* Kubernetes orchestration.
* GPU workloads.
* Online model training.
* Continuous retraining pipeline.
* Multi-model serving platform.
* Custom scheduling framework.

Ngoài ra đề bài cũng cho phép Auto-Retrain Pipeline ở mức Design-Only.

---

## EKS Assessment

### Advantages

* Hỗ trợ workload phức tạp.
* Hỗ trợ Kubernetes ecosystem.
* Hỗ trợ workload placement trên On-Demand và Spot.
* Dễ mở rộng nếu tương lai phát sinh AI platform lớn hơn.

### Disadvantages

* Chi phí vận hành cao hơn.
* Tăng độ phức tạp quản trị.
* Cần quản lý cluster lifecycle.
* Cần quản lý node groups, autoscaling và networking.
* Tạo thêm operational overhead cho capstone.

Đối với requirement hiện tại, nhiều tính năng của EKS chưa được sử dụng trực tiếp.

---

## Proposed Alternative: Amazon ECS Fargate

### Architecture

EventBridge
→ Step Functions
→ Lambda
→ ECS Fargate Service
→ AI Engine Container

### Benefits

#### Simplicity

Không cần:

* Kubernetes cluster
* Node groups
* Helm
* Karpenter
* Cluster autoscaler

#### Lower Cost

Không phát sinh chi phí EKS Control Plane.

Chi phí chỉ phát sinh khi container thực sự chạy.

#### Better FinOps Alignment

FinOps Watch là hệ thống được xây dựng nhằm giảm chi phí AWS.

Do đó chính bản thân nền tảng cũng nên tối ưu chi phí vận hành.

#### Easier Operations

CDO chỉ cần quản lý:

* Container image
* ECS service
* Auto scaling policy

Thay vì toàn bộ Kubernetes platform.

---

## Trade-off Accepted

Nhóm chấp nhận:

* Ít khả năng tùy biến workload placement hơn EKS.
* Không sử dụng Kubernetes ecosystem.

Đổi lại:

* Giảm độ phức tạp vận hành.
* Giảm chi phí nền tảng.
* Đơn giản hóa deployment.
* Phù hợp hơn với scope hiện tại của FinOps Watch.

---

## Recommendation

Trừ khi AIOps xác nhận AI Engine yêu cầu:

* GPU nodes
* Kubernetes-specific deployment
* Helm charts bắt buộc
* Multi-model serving
* Batch training workloads thực tế

CDO đề xuất chuyển từ Amazon EKS sang Amazon ECS Fargate để tối ưu chi phí, giảm operational overhead và phù hợp hơn với yêu cầu thực tế của hệ thống FinOps Watch.
