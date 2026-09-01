# 进程运行轨迹的跟踪与统计

**姓名：** 刘天浩

**学号：** 2023113228








## 实验结果截图

### `process.c` 

*首先，编写的 `process.c` 完整粘贴到此处。*

```cpp
// process.c
#define __LIBRARY__
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/times.h>

#define HZ 100

_syscall0(pid_t, fork)
_syscall1(int, setup, void*, BIOS)
_syscall0(pid_t, getpid)

/*
 * last: total CPU+I/O time in seconds (not including ready-queue waiting)
 * cpu_time: continuous CPU burst time in seconds
 * io_time: continuous I/O(sleep) burst time in seconds
 */
static void cpuio_bound(int last, int cpu_time, int io_time)
{
    struct tms t0, t1;
    clock_t du, ds;
    int do_sleep;

    while (last > 0) {
        /* CPU burst */
        if (cpu_time > 0) {
            times(&t0);
            while (1) {
                times(&t1);
                du = t1.tms_utime - t0.tms_utime;
                ds = t1.tms_stime - t0.tms_stime;
                if (((du + ds) / HZ) >= cpu_time) break;
            }
            last -= cpu_time;
        }

        /* I/O burst (sleep) */
        if (io_time > 0 && last > 0) {
            do_sleep = (io_time > last) ? last : io_time;
            sleep(do_sleep);
            last -= do_sleep;
        }

        /* If both cpu_time and io_time are 0, avoid dead loop */
        if (cpu_time == 0 && io_time == 0) break;
    }
}

int main(int argc, char *argv[])
{
    /* 6 children provides more visible interleaving in /var/process.log */
    const int nchild = 6;
    pid_t pids[6];
    int i;

    /* Workload table: (last, cpu, io) */
    int last_tbl[6] = {24, 26, 28, 30, 25, 27};
    int cpu_tbl[6]  = { 3,  2,  1,  1,  4,  2};
    int io_tbl[6]   = { 0,  1,  3,  7,  1,  5};

    for (i = 0; i < nchild; i++) {
        pids[i] = fork();
        if (pids[i] == 0) {
            /* Child */
            cpuio_bound(last_tbl[i], cpu_tbl[i], io_tbl[i]);
            exit(0);
        }
        if (pids[i] < 0) {
            printf("fork() failed at child %d\n", i);
            /* Best-effort wait already-created children */
            while (i-- > 0) wait(NULL);
            return -1;
        }
    }

    /* Parent prints child PIDs */
    printf("Child PIDs: ");
    for (i = 0; i < nchild; i++) printf("%d ", (int)pids[i]);
    printf("\n");

    /* Parent waits all children */
    for (i = 0; i < nchild; i++) wait(NULL);

    printf("All children exited.\n");
    return 0;
}

```



*然后，程序运行结果截图粘贴到此处，注意需要是 `bochs` 完整窗口。*

> ![result1](.\images\result1.png)
> [粘贴截图至此处]
>
> 



### `/var/process.log`

*首先，给出 `process.log` 内容的完整窗口截图。*

> [粘贴截图至此处]
> process.log内容较长，截取部分状态
> ![result2](.\images\result2.png)
> 



*之后，给出 `stat_log.py` 的输出结果完整窗口截图，也可以是自行编写的程序的统计结果图。*

> [粘贴截图至此处]
> ![result3](.\images\result3.png)
> 



### 修改时间片
*首先，给出修改后日志文件内容的完整窗口截图。*

> process.log内容较长，截取部分状态
> ![result4](.\images\result4.png)
>




*之后，给出修改后统计结果完整窗口截图。*

> ![result5](.\images\result5.png)
>
> 





## 实验过程记录


## 实验过程记录

*详细记录实验过程，并给出自己添加或修改的**所有**地方的**截图**。本记录基于本次实验中采用的“新版样本程序 process.c（6 子进程分层负载）+ 内核日志跟踪 + Python3 统计脚本 stat_log.py”的实现。*

---

### 1. 编写样本程序 `process.c`

本次在模板函数 `cpuio_bound(last, cpu_time, io_time)` 的基础上，编写多进程样本程序以构造可观测的调度负载。与常见的“固定 5 个子进程、参数线性递增”不同，本次样本程序一次创建 **6 个子进程**，并通过三组参数表 `last_tbl/cpu_tbl/io_tbl` 形成“纯 CPU / 轻 I/O / 重 I/O / 混合型”的分层负载，便于在 `/var/process.log` 中观察更丰富的 `R/W/J` 交错。

- 父进程：循环 `fork()` 创建 6 个子进程，保存 PID 并一次性打印 `Child PIDs:`；随后循环 `wait(NULL)`，确保所有子进程退出后父进程再退出。
- 子进程：分别调用 `cpuio_bound(last, cpu, io)`，单子进程总时长控制在 24～30 秒范围内，满足“每个子进程实际运行时间一般不超过 30 秒”的要求。
- 额外健壮性：在 `cpuio_bound()` 中加入 `cpu_time==0 && io_time==0` 的兜底退出，避免参数异常造成死循环；I/O 段对剩余 `last` 做截断，避免 `sleep()` 超时。


---

### 2. 修改 Linux 0.11 内核：建立并写入 `/var/process.log`

本实验要求在内核中维护日志文件 `/var/process.log`，记录系统从启动到关机期间所有进程的运行轨迹。日志格式为：

    pid<TAB>X<TAB>time

其中 `X ∈ {N, J, R, W, E}`，`time` 为 `jiffies`（tick）。

---

#### 2.1 添加内核态文件输出函数 `fprintf()`

在内核态无法直接使用用户态 `printf/fprintf`，本次在内核中实现了一个与 `fprintf` 类似的函数，其核心是：

- 先用 `vsprintf()` 将格式化字符串写入静态缓冲 `logbuf`；
- 当 `fd < 3` 时，认为输出到 stdout/stderr，直接调用 `sys_write`；
- 当 `fd >= 3` 时，认为输出到文件，调用 `file_write` 完成写入。

为规避高版本 bochs 环境下的缓冲/设备就绪问题，本实现对“从进程 1 的文件描述符表取文件句柄”做了保护性判断：

- 从 `task[1]->filp[fd]` 获取 `file`；
- 若 `file` 不存在或 `f_inode->i_dev` 未就绪（为 0），则直接 `return 0`，避免触发 `kernel panic: trying to get new block from nonexistant device`。

对应截图如下：

> ![2_1](.\images\2_1.png)

---

#### 2.2 在 `init/main.c` 中打开日志文件（系统启动阶段创建/清空）

为了尽早开始记录，应在文件系统初始化、标准输入输出建立之后打开日志文件。具体做法是在 `move_to_user_mode()` 后、`setup()` 完成文件系统加载并建立 fd 0/1/2（`/dev/tty0` + 两次 `dup(0)`）后，执行：

    open("/var/process.log", O_CREAT | O_TRUNC | O_WRONLY, 0666);

确保：

- 以只写方式打开；
- 若文件不存在则创建；
- 若已存在则清空；
- 权限为所有人可读写（0666）。

对应截图如下：

> ![2_2](.\images\2_2.png)

---

#### 2.3 在关键状态切换点插入日志：覆盖 N/J/R/W/E 五种状态

本实验的核心是在所有“进程状态切换点”插入日志输出，使得每一次状态变化都能写入 `/var/process.log`。本次实现覆盖了进程创建、调度切换、睡眠与唤醒、等待与退出等路径，具体如下。

---

##### 2.3.1 `fork.c`：在 `copy_process()` 记录 N 与 J

进程的真正创建发生在 `copy_process()` 中。为了准确记录生命周期起点与进入就绪队列的时刻，本次在该函数中插入两条日志：

- `N`：进程创建完成（pid 已确定）时记录新建；
- `J`：进程状态设置为可运行（就绪语义）后记录进入就绪态。

对应截图如下：

> ![2_3](.\images\2_3.png)

---

##### 2.3.2 `sched.c`：在 `sleep_on()` 记录 W，并在返回时补记录 J

`sleep_on()` 使当前进程进入不可中断睡眠（等待资源）。本次在设置 `current->state = TASK_UNINTERRUPTIBLE` 后、调用 `schedule()` 前记录 `W`（进入等待态）。此外，为体现“等待队列中被唤醒后重新进入就绪态”的语义，在 `tmp` 被置回可运行（`tmp->state=0`）后补记录 `J`。

对应截图如下：

> ![2_4](.\images\2_4.png)

---

##### 2.3.3 `sched.c`：在 `interruptible_sleep_on()` 记录 W，并对队列唤醒路径记录 J

`interruptible_sleep_on()` 使当前进程进入可中断睡眠。其内部存在“从队列中间被唤醒”的特殊情况，需要通过 `goto repeat` 重新入睡并唤醒队列头。本次在：

- `current->state = TASK_INTERRUPTIBLE` 后记录 `W`；
- 若发现 `*p && *p != current`，将队列头 `(**p).state = 0` 后记录该进程 `J`；
- 最终把 `tmp->state = 0` 后记录 `J`。

同时，为保证“等待到就绪”的转移覆盖完整，在 `wake_up()` 中也记录了 `J`（见下一小节）。

对应截图如下：

> ![2_5](.\images\2_5.png)

---

##### 2.3.4 `sched.c`：在 `wake_up()` 记录 J（等待 -> 就绪）

`wake_up()` 负责唤醒等待队列中的进程，使其重新进入可运行状态。本次在将 `(**p).state = 0` 后记录 `J`，保证等待态到就绪态的转移在日志中可见。

该实现包含在同一截图中：

> ![2_5](.\images\2_5.png)

---

##### 2.3.5 `sched.c`：信号唤醒可中断睡眠进程时记录 J

在 `schedule()` 的扫描逻辑中，如果发现处于 `TASK_INTERRUPTIBLE` 的进程收到可处理信号，会被置为 `TASK_RUNNING`（就绪语义）。本次在该路径上补充记录 `J`，使得“因信号导致的唤醒”也能进入日志。

对应截图如下：

> ![2_6](.\images\2_6.png)

---

##### 2.3.6 `sched.c`：在 `schedule()` 记录运行态 R 与运行->就绪 J

`schedule()` 是就绪进程获得 CPU 的核心入口。本次在发生真正的进程切换时记录：

- 被换下的运行进程：若其仍为 `TASK_RUNNING`，记录 `J`（运行 -> 就绪）；
- 将被切换到的进程：记录 `R`（进入运行态）。

为了避免“next==current 但仍记录”导致日志噪声，本次通过 `current->pid != task[next]->pid` 的判断，仅在 pid 不同（发生切换）时输出 `J/R` 记录。

对应截图如下：

> ![2_7](.\images\2_7.png)

---

##### 2.3.7 `sys_pause()`：记录 W（主动让出 CPU 的等待）

`sys_pause()` 常用于系统空闲或进程主动等待事件。本次在 `current->state = TASK_INTERRUPTIBLE` 后记录 `W`，并 `schedule()` 让出 CPU。由于实验环境中进程 0 会频繁调用 `sys_pause()` 造成大量噪声，因此后续统计阶段通常将进程 0 排除。

对应截图如下：

> ![2_9](.\images\2_9.png)

---

##### 2.3.8 `exit.c`：在 `do_exit()` 记录 E（退出）

进程退出在 `do_exit()` 中完成。本次在将进程置为 `TASK_ZOMBIE` 后记录 `E`，随后再 `tell_father()` 唤醒父进程并进入 `schedule()`。该顺序有利于在日志中保持“子进程先退出，父进程后被唤醒进入就绪”的时序特征。

对应截图如下：

> ![2_10](.\images\2_10.png)

---

##### 2.3.9 `sys_waitpid()`：记录 W（父进程等待子进程退出）

为完整体现“父进程等待子进程结束”的阻塞段，本次在 `sys_waitpid()` 中，当需要等待且不允许 `WNOHANG` 直接返回时，将父进程置为 `TASK_INTERRUPTIBLE` 并记录 `W`，随后 `schedule()` 进入等待。

对应截图如下：

> ![2_11](.\images\2_11.png)

---

### 3. 编译内核与运行（生成并导出 `process.log`）

1. 在 `linux-0.11/` 目录下重新编译内核：
   - `make clean` 清理旧编译产物
   - `make all` 重新编译生成镜像

2. 将 `process.c` 放入虚拟硬盘可编译目录（如 `/hdc/usr/root/`），在 Linux 0.11 中执行：
   - `gcc process.c -o process`
   - `./process`

3. 运行结束后执行：
   - `sync`  
     用于刷新文件系统缓存，确保 `/var/process.log` 真正写入磁盘（否则可能出现日志缺失或不完整）。

4. 回到宿主机挂载虚拟硬盘，导出日志文件：
   - `cp hdc/var/process.log ./`  
     将 `process.log` 拷贝到 Ubuntu 环境中，便于用脚本统计分析。


---

### 4. 运行统计脚本 `stat_log.py`（Python3 版本）并输出指标

本次统计脚本为 Python3 版本，命令行接口与指导书保持一致（支持 `-x/-m/-g`），并在解析层面对重复行、同 tick 多状态等情况做了容错处理，便于在不同实验环境下稳定统计。


---

### 5. 修改时间片并对比（`INIT_TASK`）

时间片的初始值与 `priority/counter` 密切相关，在 Linux 0.11 中由 `include/linux/sched.h` 的 `INIT_TASK` 宏初始化。通过修改 `INIT_TASK` 中的 `counter/priority` 初值（例如从默认值调整为更小或更大），可改变默认时间片尺度，从而在相同负载下观察等待时间、周转时间与吞吐量的差异。

本次在 `sched.h` 中修改 `INIT_TASK` 的相关字段后：

1. 重新 `make clean && make all` 编译内核；
2. 启动后重复运行同一 `process` 工作负载；
3. 导出新的 `/var/process.log`；
4. 用相同统计口径再次运行 `stat_log.py`，对比修改前后的统计结果。

对应截图如下（展示 `INIT_TASK` 修改位置）：

> ![5](.\images\5.png)


---










## 回答如下问题：

### 1. 结合自己的体会，谈谈从程序设计者的角度看，单进程编程和多进程编程最大的区别是什么？

从程序设计者视角来看，单进程与多进程编程的本质差异在于“控制对象”的数量与由此带来的复杂度来源不同。单进程程序通常沿着一条确定的控制流顺序推进，状态变化主要发生在同一执行上下文内，开发时更容易用线性逻辑推演程序行为，调试也更直观；但一旦遇到 I/O 阻塞或长耗时计算，整体推进会被拖慢，且难以充分利用并行硬件资源。多进程编程则将任务拆分到多个独立的执行实体中并发推进，能够提升系统吞吐与资源利用率，但程序行为不再仅由代码顺序决定，还取决于调度时序与竞争关系，必须额外处理进程间协作、同步互斥、共享资源一致性、异常退出与回收等问题。换言之，多进程的关键挑战是从“写对功能”扩展为“在不确定交错下仍保持正确性与可控性”。



### 2. 你是如何修改时间片的？仅针对样本程序建立的进程，在修改时间片前后，`log` 文件的统计结果（不包括 Graphic）都是什么样？结合你的修改分析一下为什么会这样变化，或者为什么没变化？

时间片的调整通过修改 Linux 0.11 中 `include/linux/sched.h` 里的 `INIT_TASK` 初始化宏实现：该宏给系统初始进程设置了默认的 `priority` 与 `counter`，而新创建进程在 `copy_process()` 中会将 `counter` 重新设为 `priority`，因此它们等价地决定了时间片的初始尺度。本次将默认值由 15 调整为 10，随后重新编译内核并在同一套样本负载下重复采集 `/var/process.log`，再用统计脚本仅对样本程序产生的子进程做计算对比（排除 0/1 等系统进程干扰）。

从统计结果表现看，时间片减小后，进程更容易被抢占与轮转，I/O 型或交互式进程在从等待态被唤醒后往往能更快获得 CPU，平均等待时间倾向于下降；同时，由于更频繁发生调度切换，运行段被切碎，上下文切换带来的额外开销会更突出，若负载以纯 CPU 计算为主，周转时间与吞吐量的改善可能不明显，甚至会因切换成本略有波动。相反，若将时间片调大，切换次数减少、单次连续运行更长，CPU 密集任务更“吃满”时间片，但 I/O 密集进程被唤醒后可能需要等待更久才轮到运行，从而抬升等待时间与周转时间。总体而言，实验现象反映了时间片大小在“响应性/公平性”和“切换开销/吞吐”之间的权衡：工作负载越偏 I/O 与交互，较小时间片越可能带来更直观的等待时间改善；负载越偏 CPU 计算，时间片变化对统计指标的影响则可能更有限。



## （可选）总结与反思

本次实验围绕“记录—分析—对比”三个环节展开：先通过多进程样本程序构造可控负载，再在 Linux 0.11 内核中补齐进程状态转换点的日志输出，最终基于 `/var/process.log` 计算等待时间、周转时间与吞吐量等指标，并通过修改时间片进行对比验证。通过这一流程，进程从创建到退出的状态轨迹不再停留在概念层面，而是以可复核的数据形式呈现出来，使调度策略的效果能够被量化讨论。

实现过程中较有挑战的部分主要在环境与日志可靠性：高版本 Bochs 可能引发缓冲/设备就绪相关问题，需要在内核态写文件时做更严格的就绪性判断，并在统计时避免将不稳定的系统进程轨迹混入样本分析；同时，状态切换点分散在 fork、调度、睡眠/唤醒、等待与退出等多条路径上，任何遗漏都会导致统计口径不完整。进一步的体会是，调度算法的“好坏”往往依赖负载类型，时间片只是其中一个关键参数；只有在可观测的轨迹与一致的统计口径基础上，才能对调度调整给出可信的解释与结论。
