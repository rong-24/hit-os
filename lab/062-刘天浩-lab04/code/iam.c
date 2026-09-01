#define __LIBRARY__
#include <unistd.h>
#include <stdio.h>

#ifndef __NR_iam
#define __NR_iam 72
#endif

_syscall1(int, iam, const char*, name);

int main(int argc, char *argv[])
{
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <name>\n", argv[0]);
        return 1;
    }

    if (iam(argv[1]) < 0) {
        perror("iam");
        return 1;
    }

    /* 为避免影响评分脚本，成功时不额外输出 */
    return 0;
}
