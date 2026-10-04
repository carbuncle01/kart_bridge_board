#ifndef USBD_CONF_H
#define USBD_CONF_H

#include <stdlib.h>
#include <string.h>

#include "stm32g0xx_hal.h"

#define USBD_MAX_NUM_INTERFACES 1U
#define USBD_MAX_NUM_CONFIGURATION 1U
#define USBD_MAX_STR_DESC_SIZ 512U
#define USBD_SUPPORT_USER_STRING_DESC 0U
#define USBD_SELF_POWERED 0U
#define USBD_DEBUG_LEVEL 0U
#define USBD_LPM_ENABLED 0U

void *jpbb_usbd_malloc(uint32_t size);
void jpbb_usbd_free(void *pointer);

#define USBD_malloc jpbb_usbd_malloc
#define USBD_free jpbb_usbd_free
#define USBD_memset memset
#define USBD_memcpy memcpy
#define USBD_Delay HAL_Delay

#if (USBD_DEBUG_LEVEL > 0U)
#define USBD_UsrLog(...) do { } while (0)
#define USBD_ErrLog(...) do { } while (0)
#define USBD_DbgLog(...) do { } while (0)
#else
#define USBD_UsrLog(...) do { } while (0)
#define USBD_ErrLog(...) do { } while (0)
#define USBD_DbgLog(...) do { } while (0)
#endif

#endif
