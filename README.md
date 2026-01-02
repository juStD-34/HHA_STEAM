# Tay Application

## Huong dan cai dat va chay

## Cach clone repo

```bash
git clone https://github.com/juStD-34/HHA_STEAM.git
```

Su dung cac file trong thu muc `Huong dan`:

### Cai dat
- macOS: `Huong dan/cai_dat_mac.sh`
- Windows: `Huong dan/cai_dat_win.bat`

### Chay ung dung
- macOS: `Huong dan/chay_mac.sh`
- Windows: `Huong dan/chay_win.bat`

---

## Work-flow (Mermaid)

```mermaid
flowchart LR
    classDef action fill:#1f2937,stroke:#38bdf8,stroke-width:1px,color:#e2e8f0
    classDef device fill:#0f172a,stroke:#34d399,stroke-width:1px,color:#e2e8f0
    classDef server fill:#0b1220,stroke:#f59e0b,stroke-width:1px,color:#e2e8f0
    classDef output fill:#111827,stroke:#a78bfa,stroke-width:1px,color:#e2e8f0

    subgraph UI["Giao diện người dùng"]
        A[User mở ứng dụng /test]:::action
        B[Làm bài kiểm tra tính khéo léo - Wire Loop]:::action
        E[Làm bài kiểm tra tốc độ phản xạ]:::action
        F[Chat với AI agent để làm test DISC]:::action
    end

    subgraph Device["Thiết bị & Dữ liệu"]
        C[Thiết bị gửi thông tin đến server]:::device
    end

    subgraph Server["Xử lý trên server"]
        D[Server cập nhật trạng thái và hiển thị lên UI]:::server
        G[Tổng hợp kết quả nghề nghiệp]:::server
        H[Tìm trường đại học có đào tạo các ngành phù hợp]:::output
    end

    A --> B
    B --> C --> D
    A --> E --> G
    A --> F --> G
    D --> G --> H
```
