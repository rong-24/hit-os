#define __LIBRARY__
#include <unistd.h>
#include <stdio.h>

#ifndef __NR_whoami
#define __NR_whoami 73
#endif

_syscall2(int, whoami, char*, name, unsigned int, size);

int main(void)
{
    char buf[32];
    int ret = whoami(buf, sizeof(buf));

    if (ret < 0) {
        perror("whoami");
        return 1;
    }

    printf("%s\n", buf);
    return 0;
}
