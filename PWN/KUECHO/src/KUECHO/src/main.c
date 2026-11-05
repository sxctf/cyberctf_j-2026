#include <stdio.h>
#include <string.h>

void v_function() {
    char buf[64];
    printf("Stack address leak: %p\n", buf);
    printf("Enter some text: ");
    fgets(buf, 80, stdin);
    puts("=== ECHO SERVICE v0.1337 ===");
    printf(buf);
    printf("\nPayload: ");
    fgets(buf, 128, stdin);
}

int main() {
    setvbuf(stdout, NULL, _IONBF, 0);
    puts("Welcom to baby++ pwn");
    v_function();
    printf("Goodbye baby");
    return 0;
}
