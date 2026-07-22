import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

WINDOW = 4
HORIZON = 3

class PureGCNConv(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.lin = nn.Linear(in_ch, out_ch)

    def forward(self, x, A_hat):
        # x: (B, N, F)
        x = self.lin(x)
        x = torch.sparse.mm(A_hat, x)
        return x
        

class STGCNBlock(nn.Module):
    def __init__(self, in_ch, spatial_ch, out_ch):
        super().__init__()
        self.tconv1 = nn.Conv2d(in_ch, spatial_ch, kernel_size=(1, 3), padding=(0, 1))
        self.bn1 = nn.BatchNorm2d(spatial_ch)
        self.gcn = PureGCNConv(spatial_ch, spatial_ch)
        self.tconv2 = nn.Conv2d(spatial_ch, out_ch, kernel_size=(1, 3), padding=(0, 1))
        self.bn2 = nn.BatchNorm2d(out_ch)
        self.residual = nn.Conv2d(in_ch, out_ch, (1, 1)) if in_ch != out_ch else nn.Identity()

    def _batched_gcn(self, x, A_hat):
        """GCN batched over B, sequential over T (chỉ 4 vòng lặp)."""
        B, N, C, T = x.size()
        offsets = torch.arange(B, device=x.device) * N                 # (B,)

        outs = []
        for t in range(T):
            x_t = x[:, :, :, t].reshape(B * N, C)     # (B*N, C)
            out_t = F.relu(self.gcn(x_t, A_hat))    # (B*N, C)
            outs.append(out_t.reshape(B, N, C))
        return torch.stack(outs, dim=-1)                # (B, N, C, T)

    def forward(self, x, A_hat):
        # x: (B, N, C_in, T)
        res = self.residual(x.permute(0, 2, 1, 3)).permute(0, 2, 1, 3)

        # Temporal Conv 1
        x = x.permute(0, 2, 1, 3)                     # (B, C, N, T)
        x = F.relu(self.bn1(self.tconv1(x)))
        x = x.permute(0, 2, 1, 3)                     # (B, N, C', T)

        # Spatial GCN (batched)
        x = self._batched_gcn(x, A_hat)

        # Temporal Conv 2
        x = x.permute(0, 2, 1, 3)
        x = F.relu(self.bn2(self.tconv2(x)))
        x = x.permute(0, 2, 1, 3)                     # (B, N, C_out, T)

        return x + res

class STGCN(nn.Module):
    def __init__(self, num_nodes, in_features=1, window=WINDOW, horizon=HORIZON):
        super().__init__()
        self.block1 = STGCNBlock(in_features, 32, 32)
        self.block2 = STGCNBlock(32, 32, 16)
        self.fc = nn.Linear(16 * window, horizon)

    def forward(self, x, A_hat):
        # x: (B, N, F=1, T=4)
        x = self.block1(x, A_hat)
        x = self.block2(x, A_hat)
        B, N, C, T = x.size()
        x = x.reshape(B, N, C * T)
        return self.fc(x)           # (B, N, horizon)
        

class STGCNInference:
    def __init__(self, pth_path, edge_index):
        self.pth_path = pth_path
        self.edge_index = edge_index
        self.A_hat = self.build_a_hat(edge_index, num_nodes=edge_index.max().item() + 1)
        ckpt = torch.load(self.pth_path, weights_only=False)
        self.model = STGCN(num_nodes=ckpt['num_nodes'])
        self.model.load_state_dict(ckpt['model_state_dict'])
        self.train_mean = ckpt['train_mean']
        self.train_std = ckpt['train_std']
        total_params = sum(p.numel() for p in self.model.parameters())
        print(f"Model parameters: {total_params:,}")
        print(self.model)
    
    def predict(self, x_4_frames):
        # Input: Tensor (1, 103662, 1, 4)
        self.model.eval()
        with torch.no_grad():
            x = torch.tensor(x_4_frames, dtype=torch.float32)
            x = (x - self.train_mean) / self.train_std
            output = self.model(x, self.A_hat)
            output = output * self.train_std + self.train_mean
            output = torch.clamp(output, min=5.0, max=100.0)
        return output.numpy()
    
    def build_a_hat(self, edge_index, num_nodes):
        # Bước 1: Tạo self-loops (Danh sách các cạnh tự nối từ node 0->0, 1->1, ...)
        self_loops = torch.arange(end = num_nodes).unsqueeze(0).repeat(2, 1)  # (2, N)
        edge_index_with_loops = torch.cat([edge_index, self_loops], dim=1)
        
        # Bước 2: Tính Degree (Bậc) của mỗi node
        deg = torch.zeros(num_nodes, dtype=torch.float32)
        deg = torch.bincount(edge_index_with_loops[0], minlength=num_nodes).float()
        
        # Bước 3: Tính hệ số chuẩn hóa (deg_inv_sqrt)
        deg_inv_sqrt = 1.0 / torch.sqrt(deg)
        deg_inv_sqrt[deg_inv_sqrt == float('inf')] = 0.0
        
        # Bước 4: Gắn trọng số cho từng cạnh
        weights = deg_inv_sqrt[edge_index_with_loops[0]] * deg_inv_sqrt[edge_index_with_loops[1]]
        
        # Bước 5: Đóng gói thành Ma trận Thưa (Sparse Tensor)
        return torch.sparse_coo_tensor(edge_index_with_loops, weights, size=(num_nodes, num_nodes)).coalesce()