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
