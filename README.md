# Tay Application

## Huong dan cai dat va chay

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
flowchart TD
    A[User mở ứng dụng /test] --> B[Làm bài kiểm tra tính khéo léo - Wire Loop]
    B --> C[Thiết bị gửi thông tin đến application]
    C --> D[Server cập nhật trạng thái và hiển thị lên UI]
    A --> E[Làm bài kiểm tra tốc độ phản xạ trên application]
    A --> F[Chat với AI agent để làm test DISC]
    D --> G[Tổng hợp kết quả nghề nghiệp]
    E --> G
    F --> G
    G --> H[Tìm trường đại học có đào tạo các ngành]
```
