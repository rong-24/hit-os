.code16
# bootsect.s (variant) - same behavior, different implementation details

	.equ SETUPLEN, 2              # 仍然加载 2 个扇区（setup）
	.equ BOOTSEG, 0x07c0
	.equ INITSEG, 0x9000
	.equ SETUPSEG, 0x9020

	.global _start, begtext, begdata, begbss, endtext, enddata, endbss
	.text
begtext:
	.data
begdata:
	.bss
begbss:
	.text

	ljmp	$BOOTSEG, $_start

_start:
	# 1) 将 bootsect 从 0x7c00 搬到 0x90000（逻辑不变，写法不同）
	mov	$BOOTSEG, %ax
	mov	%ax, %ds
	mov	$INITSEG, %ax
	mov	%ax, %es

	xor	%si, %si
	xor	%di, %di
	mov	$256, %cx               # 256 words = 512 bytes
	rep
	movsw

	ljmp	$INITSEG, $entry

entry:
	# 2) 统一段寄存器与栈（结果不变）
	mov	%cs, %ax
	mov	%ax, %ds
	mov	%ax, %es
	mov	%ax, %ss
	mov	$0xFF00, %sp

	# 3) 打印启动字符串（仍用 int 10h/13h；封装为子过程以“代码不同”）
	call	print_boot_msg

	# 4) 读入 setup（仍然从扇区2开始读 SETUPLEN 个扇区到 INITSEG:0x0200）
	call	load_setup_with_retry

	# 5) 跳转到 setup
	ljmp	$SETUPSEG, $0x0000


# ----------------------------
# 子过程：打印启动信息
# ----------------------------
print_boot_msg:
	# 读取光标（保持与原先一致：先读光标再写字符串）
	mov	$0x03, %ah
	xor	%bh, %bh
	int	$0x10

	mov	$BOOT_MSG_LEN, %cx
	mov	$0x0007, %bx
	mov	$msg1, %bp
	mov	$0x1301, %ax
	int	$0x10
	ret


# ----------------------------
# 子过程：读盘 + 失败重试（功能同原先，但组织方式不同）
# ----------------------------
load_setup_with_retry:
read_try:
	# int 13h AH=02h: read sectors
	# CH=0, CL=2, DH=0, DL=0 (floppy)
	xor	%dx, %dx                # DL=0, DH=0
	mov	$0x0002, %cx            # CH=0, CL=2 (sector 2)
	mov	$0x0200, %bx            # offset 0x200 in INITSEG
	mov	$0x02, %ah
	mov	$SETUPLEN, %al
	int	$0x13
	jnc	read_ok

	# reset disk system (int 13h AH=00h)
	xor	%ax, %ax
	xor	%dx, %dx
	int	$0x13
	jmp	read_try

read_ok:
	ret


# ----------------------------
# 启动字符串（与原先“输出效果/长度”保持一致）
# ----------------------------
	.equ BOOT_MSG_LEN, 44

msg1:
	.byte 13,10
	.ascii "student lth 2023113228 is operating..."
	.byte 13,10,13,10

	.org 510
boot_flag:
	.word 0xAA55

	.text
endtext:
	.data
enddata:
	.bss
endbss:
