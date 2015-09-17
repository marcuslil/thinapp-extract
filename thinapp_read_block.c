#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char *argv[])
{
    if (argc == 3) {
        uint32_t inbytes = atoi(argv[1]);
        uint32_t outbytes = atoi(argv[2]);
        char *out = malloc(outbytes);
        char *in = malloc(inbytes);
        uint32_t i;
        for (i = 0; i != inbytes; i++) {
            in[i] = fgetc(stdin);
        }
        i = read_block(in, out);
        if (i != outbytes) {
            printf("wrong nr bytes returned\n");
            return -1;
        }
        for (i = 0; i != outbytes; i++)
            fputc(out[i], stdout);
        return 0;
    } else if (argc != 3) {
        printf("fail\n");
        return -1;
    }
}

int32_t read_block(uint8_t * input, uint8_t * output, u_int32_t nr_out_bytes)
{
    if (*input == 0xd8 || *input == 0xd7) {
        uint32_t r = decompress(input + 1, output);
        if (*input == 0xd8)
            while (nr_out_bytes--)
                *output++ ^= 0xf0;
        return r;
    } else {
        memcpy(output, input + 1, nr_out_bytes);
        return nr_out_bytes;
    }
}

uint32_t step(u_int32_t * src_reg, u_int32_t ** src_ptr, uint32_t bits)
{
    uint8_t carry;
    u_int32_t ret = 0;
    while (bits--) {
        carry = *src_reg >= 0x80000000;
        *src_reg <<= 1;
        if (*src_reg == 0) {
            *src_reg = *(*src_ptr)++;
            carry = *src_reg >= 0x80000000;
            *src_reg = (*src_reg << 1) + 1;
        }
        ret = (ret << 1) + carry;
    }
    return ret;
}

uint32_t step2(u_int32_t * src_reg, u_int32_t ** src_ptr)
{
    u_int32_t ret = 1;
    do {
        ret = (ret << 1) + step(src_reg, src_ptr, 1);
    }
    while (step(src_reg, src_ptr, 1));
    return ret;
}

void copy_and_increment(char *src, char **dst, uint32_t count)
{
    while (count--)
        *(*dst)++ = *src++;
}

int32_t decompress(uint32_t * src_arg, char *dst_arg)
{
    uint32_t *src_ptr = src_arg;
    char *dst = dst_arg;
    uint32_t src_reg = 0x80000000;

    uint32_t copy_offset = 1;
    uint32_t copy_nr_bits = 8;
    uint32_t shrink_bits;
    uint8_t shrink_offset;

    while (1) {
        if (step(&src_reg, &src_ptr, 1) == 1) {
            // applying shrink
            *dst++ = step(&src_reg, &src_ptr, shrink_bits) + shrink_offset;
        } else if (step(&src_reg, &src_ptr, 1) == 1) {
            uint32_t val1, size;

            size = step2(&src_reg, &src_ptr) - 2;
            if (size != 0) {
                val1 = step(&src_reg, &src_ptr, copy_nr_bits)
                        | (size - 1) << copy_nr_bits;
                size = step2(&src_reg, &src_ptr);
                if (val1 >= 0x10000)
                    size += 3;
                else if (val1 >= 0x37ff)
                    size += 2;
                else if (val1 >= 0x27f)
                    size += 1;
                else if (val1 <= 0x7f)
                    size += 4;
                copy_offset = val1;
            } else {
                size = step2(&src_reg, &src_ptr);
            }
            copy_and_increment(dst - copy_offset, &dst, size);
        } else if (step(&src_reg, &src_ptr, 1) == 0) {
            uint32_t val, size;
            val = step(&src_reg, &src_ptr, 7);
            size = step(&src_reg, &src_ptr, 2) + 2;
            if (val == 0) {
                if (size == 0x2)
                    return dst - dst_arg;
                copy_nr_bits = step(&src_reg, &src_ptr, size + 1);
            } else {
                copy_offset = val;
                copy_and_increment(dst - copy_offset, &dst, size);
            }
        } else {
            uint32_t val = step(&src_reg, &src_ptr, 4);

            if (val == 1) {
                *dst++ = 0;
            } else if (val > 1) {
                *(dst++) = *(dst - val);
            } else if (step(&src_reg, &src_ptr, 1) == 0) {
                // shrink mode settings
                shrink_bits = step(&src_reg, &src_ptr, 1) + 7;
                if (shrink_bits == 0x8)
                    shrink_offset = 0;
                else
                    shrink_offset = step(&src_reg, &src_ptr, 8);
            } else {
                // copy 100 mode
                do {
                    uint32_t i;
                    for (i = 0; i != 0x100; i++)
                        *dst++ = step(&src_reg, &src_ptr, 8);
                }
                while (step(&src_reg, &src_ptr, 1) == 1);
            }
        }
    }
}
