/*
 * Minimal STM32F407 lab firmware image.
 *
 * This file documents the bytes in firmware.bin. The emulator loads the raw
 * binary at 0x00000000 as the boot alias and at 0x08000000 as flash. The
 * vector table lives at the boot alias for Unicorn MCLASS startup.
 */

.syntax unified
.thumb

.word 0x20020000      /* initial SP: top of mapped SRAM */
.word reset_handler + 1

reset_handler:
    movs r0, #0
loop:
    adds r0, #1
    b loop
