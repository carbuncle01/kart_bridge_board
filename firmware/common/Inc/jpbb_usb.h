#ifndef JPBB_USB_H
#define JPBB_USB_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

void jpbb_usb_init(void);
void jpbb_usb_poll(void);
bool jpbb_usb_is_configured(void);
bool jpbb_usb_read_line(char *buffer, size_t capacity);
bool jpbb_usb_write(const char *text);
bool jpbb_usb_write_bytes(const uint8_t *data, uint16_t length);
void jpbb_usb_receive_from_isr(const uint8_t *data, uint32_t length);

#endif
