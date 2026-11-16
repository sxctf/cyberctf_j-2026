#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/cdefs.h>
#include "string.h"
#include "stdint.h"


typedef struct {
    uint16_t device_type;
    uint16_t status;
    void (*log_callback)(char*);
} CtosHeader;


typedef struct {
    CtosHeader* header;
    char node_name[32];
    void* extra_data;
} CtosSession;

void default_log(char* msg) {
    puts(msg);
    // В реальной системе тут был бы вывод в файл.
    // Для CTF это просто валидный адрес функции, который игрок попытается перезаписать.
}

__attribute__((visibility("default")))
void* ctos_alloc_session(const char* node_name, uint16_t d_type) {
    CtosSession* sessions = (CtosSession*)malloc(sizeof(CtosSession));

    sessions->header  = (CtosHeader*)malloc(sizeof(CtosHeader));

    sessions->header->device_type = d_type;
    sessions->header->status = 1;
    sessions->header->log_callback = default_log;

    strncpy(sessions->node_name, node_name, 31);
    sessions->node_name[31] = '\0';

    size_t chunk_size = 0x20;

    switch (d_type) {
        case 3:
        case 9:
        case 11:
            chunk_size = 0x500;
            break;
        case 2:
        case 10:
        case 12:
        case 13:
        case 18:
            chunk_size = 0x150;
            break;
        default:
            chunk_size = 0x30;
            break;
    }
    sessions->extra_data = malloc(chunk_size);
    return (void*)sessions;
}

__attribute__((visibility("default")))
void ctos_free_session(void* ptr){
    if (ptr == NULL) return;

    CtosSession* sessions = (CtosSession*)ptr;
    if (sessions->extra_data) {
        free(sessions->extra_data);
    }

    if (sessions->header){
        free(sessions->header);
    }
    free(sessions);
    // ВАЖНО ДЛЯ PWN:
    // Функция завершилась. Память отдана операционной системе (аллокатору кучи).
    // Аллокатор запишет сюда служебные адреса (fd/bk указатели).
    // При этом указатель `ptr` внутри TUI всё еще существует!
    // В современном Linux (glibc) маленькие блоки памяти (до 0x410 байт) при удалении попадают в так называемый Tcache (Thread Local Caching). В Tcache хранятся адреса самой кучи (Heap Leak).
    // Блоки больше 0x410 байт попадают в Unsorted Bin. Главная особенность Unsorted Bin в том, что аллокатор записывает в освобожденный чанк адрес внутри libc (main_arena+96).
    // Таким образом, заставив TUI выделить устройство типа 3, а затем удалив его, игрок сможет прочитать из панели телеметрии адрес libc, вычислить базовый адрес библиотеки и обойти защиту ASLR.

}

// gcc — компилятор GNU C.
// -shared — говорит компилятору создать динамическую библиотеку, а не исполняемый файл.
// -fPIC (Position Independent Code) — обязательный флаг для динамических библиотек. Код должен уметь работать по любому адресу в памяти, куда бы его ни загрузила ОС (привет, ASLR).
// -o libctos.so — имя выходного файла.

__attribute__((visibility("default")))
void ctos_logger(void* ptr){
    if (ptr == NULL) return;
    CtosSession* session = (CtosSession*)ptr;

    if (session->header && session->header->log_callback) {
        // Вызываем функцию!
        // В норме это default_log("ctOS_Camera_1234")
        // При взломе это будет system("cat flag.txt")
        session->header->log_callback(session->node_name);
    }

}
