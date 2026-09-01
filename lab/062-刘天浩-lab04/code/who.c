#define __LIBRARY__
#include <unistd.h>
#include <errno.h>
#include <asm/segment.h>

#define NAME_MAX_LEN 23
#define KBUF_SIZE    (NAME_MAX_LEN + 1)

static char kname[KBUF_SIZE];
static int  kname_len;

int sys_iam(const char *name)
{
    char tmp[KBUF_SIZE];
    int i;
    char c;

    /* 先拷贝并做长度判定：超过 23 直接失败，不污染已保存的名字 */
    for (i = 0; i < KBUF_SIZE; i++) {
        c = get_fs_byte(name + i);
        tmp[i] = c;

        if (c == '\0') {
            /* i 即长度（不含 '\0'） */
            kname_len = i;
            /* 提交到内核保存区 */
            for (int j = 0; j <= i; j++) kname[j] = tmp[j];
            return kname_len;
        }
    }

    /* 走到这里说明前 24 字节都没有 '\0' => 长度 >= 24 > 23 */
    return -EINVAL;
}

int sys_whoami(char *name, unsigned int size)
{
    /* 需要 len + 1 的空间以容纳 '\0' */
    if (size < (unsigned int)(kname_len + 1))
        return -EINVAL;

    for (int i = 0; i < kname_len; i++)
        put_fs_byte(kname[i], name + i);

    put_fs_byte('\0', name + kname_len);
    return kname_len;
}
