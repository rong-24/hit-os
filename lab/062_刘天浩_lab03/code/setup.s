.code16
# setup.s (variant) - same output, different implementation details

	.equ SETUPSEG, 0x9020
	.equ INITSEG,  0x9000

	.global _start, begtext, begdata, begbss, endtext, enddata, endbss
	.text
begtext:
	.data
begdata:
	.bss
begbss:
	.text

_start:
	# 1) 段寄存器初始化
	mov	$SETUPSEG, %ax
	mov	%ax, %ds
	mov	%ax, %es

	# 2) 打印提示：Now we are in SETUP
	lea	msg_setup, %si
	mov	$SETUP_MSG_LEN, %cx
	call	print_str

	call	print_nl

	# 3) 读取扩展内存大小（int 15h, ah=88h），并保存到 memory
	mov	$0x88, %ah
	int	$0x15
	mov	%ax, memory

	# 打印 "Memory: " + memory(hex) + " KB"
	lea	msg_memory, %si
	mov	$9, %cx
	call	print_str

	mov	memory, %dx
	call	print_hex16

	lea	msg_kb, %si
	mov	$3, %cx
	call	print_str

	call	print_nl

	# 4) 复制第一硬盘参数表 16 字节到 0x90080
	call	copy_disk1_table

	# 5) 统一设置 ES=INITSEG，直接用段覆盖读取字段
	mov	$INITSEG, %ax
	mov	%ax, %es

	# Cylinders
	lea	msg_cyl, %si
	mov	$11, %cx
	call	print_str

	movw	%es:0x80, %dx
	call	print_hex16
	call	print_nl

	# Heads
	lea	msg_heads, %si
	mov	$7, %cx
	call	print_str

	movw	%es:0x82, %dx
	and	$0x00ff, %dx
	call	print_hex16
	call	print_nl

	# Sectors
	lea	msg_sectors, %si
	mov	$9, %cx
	call	print_str

	movw	%es:0x8E, %dx
	and	$0x00ff, %dx
	call	print_hex16
	call	print_nl

hang:
	jmp	hang


# ----------------------------
# print_str: DS:SI 指向字符串，CX=长度
# 使用 int 10h/0Eh 逐字符输出
# ----------------------------
print_str:
	push	%ax
	push	%bx
	push	%cx
	push	%si

	mov	$0x0007, %bx            # BH=page(0), BL=attr(7) - 对 0Eh 实际主要用 BH
print_str_loop:
	lodsb
	mov	$0x0E, %ah
	int	$0x10
	loop	print_str_loop

	pop	%si
	pop	%cx
	pop	%bx
	pop	%ax
	ret


# ----------------------------
# print_nl: CR/LF
# ----------------------------
print_nl:
	push	%ax
	mov	$0x0E, %ah
	mov	$0x0D, %al
	int	$0x10
	mov	$0x0A, %al
	int	$0x10
	pop	%ax
	ret


# ----------------------------
# print_hex16: 以 4 个十六进制字符输出 DX（实现方式与原先不同）
# ----------------------------
print_hex16:
	push	%ax
	push	%bx
	push	%cx
	push	%dx

	mov	%dx, %bx                # 用 BX 做移位寄存器
	mov	$4, %cx

hex_loop:
	# 取高 4 位
	mov	%bx, %ax
	shr	$12, %ax
	and	$0x000F, %ax

	# 0-9 / A-F
	cmp	$10, %al
	jl	hex_is_digit
	add	$7, %al
hex_is_digit:
	add	$0x30, %al
	mov	$0x0E, %ah
	int	$0x10

	# 左移 4 位，准备下一位
	shl	$4, %bx
	loop	hex_loop

	pop	%dx
	pop	%cx
	pop	%bx
	pop	%ax
	ret


# ----------------------------
# copy_disk1_table: 从中断向量 0x41 取得第一硬盘参数表，复制 16B 至 ES:DI=INITSEG:0x0080
# ----------------------------
copy_disk1_table:
	push	%ax
	push	%bx
	push	%cx
	push	%dx
	push	%si
	push	%di
	push	%ds
	push	%es

	# DS=0 以访问中断向量表
	xor	%ax, %ax
	mov	%ax, %ds

	# 取 INT 41h 指针到 DS:SI
	lds	(4*0x41), %si

	# 目标：INITSEG:0x0080
	mov	$INITSEG, %ax
	mov	%ax, %es
	mov	$0x0080, %di
	mov	$0x10, %cx
	rep
	movsb

	# 恢复 DS 回 SETUPSEG，后续字符串读取继续正常
	mov	$SETUPSEG, %ax
	mov	%ax, %ds

	pop	%es
	pop	%ds
	pop	%di
	pop	%si
	pop	%dx
	pop	%cx
	pop	%bx
	pop	%ax
	ret


# ----------------------------
# 数据区（字符串内容保持一致，长度常量显式给出）
# ----------------------------
	.equ SETUP_MSG_LEN, 19

msg_setup:
	.byte 13,10
	.ascii "Now we are in SETUP"
	.byte 13,10,13,10

msg_memory:
	.ascii "Memory: "
msg_kb:
	.ascii " KB"
msg_cyl:
	.ascii "Cylinders: "
msg_heads:
	.ascii "Heads: "
msg_sectors:
	.ascii "Sectors: "

memory:
	.word 0

	# 保留（即使不强制需要），以保证“结构/接口观感”与原先一致
	.org 510
boot_flag:
	.word 0xAA55

	.text
endtext:
	.data
enddata:
	.bss
endbss:
