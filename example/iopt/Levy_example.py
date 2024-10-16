from fealpy.backend import backend_manager as bm
from fealpy.opt.Levy import levy
import time
import matplotlib.pyplot as plt
from matplotlib.markers import MarkerStyle
# bm.set_backend('pytorch')

start_time = time.perf_counter()

# 定义设备
device = 'cpu'
# device = 'cuda'

n = 1000000
num = 100
iter_num = 1

L = bm.zeros([1 + n * iter_num, 2, num], device=device)
B = bm.zeros([1 + n * iter_num, 2, num], device=device)
L[0, :] = L[0, :, :] + 10
B[0, :] = B[0, :, :] + 10

for i in range(iter_num):
    levy_steps = levy(n, 2, 1.5, num, device)
    randn_steps = bm.random.randn(n, 2, num)

    levy_steps_tensor = bm.array(levy_steps, device=device, dtype=bm.float32)
    randn_steps_tensor = bm.array(randn_steps, device=device, dtype=bm.float32)

    L[n * i : (i + 1) * n, :, :] = bm.cumsum(levy_steps_tensor, dim=0) + 10
    B[n * i : (i + 1) * n, :, :] = bm.cumsum(randn_steps_tensor, dim=0) + 10

end_time = time.perf_counter()
running_time = end_time - start_time
print("Running time:", running_time)

# L_cpu = L.cpu().numpy()
# B_cpu = B.cpu().numpy()


# for particle in range(0, 1):
#     L_x_vals = L_cpu[:, 0, particle]  
#     L_y_vals = L_cpu[:, 1, particle]  
#     B_x_vals = B_cpu[:, 0, particle]  
#     B_y_vals = B_cpu[:, 1, particle]  
#     plt.figure()
#     plt.plot(L_x_vals, L_y_vals, '-', color = 'blue')
#     plt.plot(B_x_vals, B_y_vals, '-', color = 'black')
#     plt.scatter(L_x_vals[0], L_y_vals[0], marker=MarkerStyle('*'), color='red', s=500) 

# plt.show()