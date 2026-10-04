cmake_minimum_required(VERSION 3.22)

set(CMAKE_TOOLCHAIN_FILE
    "${CMAKE_CURRENT_LIST_DIR}/cmake/arm-none-eabi.cmake"
    CACHE FILEPATH "ARM GNU toolchain file")

project(kart_bridge_firmware C ASM)

set(KART_STEP "step1_safe_boot" CACHE STRING "Firmware step directory to build")
set(STM32CUBE_G0_PATH "" CACHE PATH "Path to a recursive STM32CubeG0 checkout")

if(NOT STM32CUBE_G0_PATH)
  message(FATAL_ERROR
    "Set STM32CUBE_G0_PATH to STM32CubeG0 v1.6.3 or newer. "
    "See firmware/README.md.")
endif()

set(STEP_DIR "${CMAKE_CURRENT_LIST_DIR}/${KART_STEP}")
if(NOT EXISTS "${STEP_DIR}/main.c")
  message(FATAL_ERROR "Unknown KART_STEP: ${KART_STEP}")
endif()

set(HAL_DIR "${STM32CUBE_G0_PATH}/Drivers/STM32G0xx_HAL_Driver")
set(CMSIS_DIR "${STM32CUBE_G0_PATH}/Drivers/CMSIS")
set(USB_DIR "${STM32CUBE_G0_PATH}/Middlewares/ST/STM32_USB_Device_Library")
set(STARTUP
  "${CMSIS_DIR}/Device/ST/STM32G0xx/Source/Templates/gcc/startup_stm32g0b1xx.s")

foreach(required
    "${HAL_DIR}/Src/stm32g0xx_hal.c"
    "${CMSIS_DIR}/Device/ST/STM32G0xx/Source/Templates/system_stm32g0xx.c"
    "${USB_DIR}/Core/Src/usbd_core.c"
    "${STARTUP}")
  if(NOT EXISTS "${required}")
    message(FATAL_ERROR
      "STM32CubeG0 is missing ${required}. Clone it with --recursive.")
  endif()
endforeach()

set(HAL_SOURCES
  "${HAL_DIR}/Src/stm32g0xx_hal.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_cortex.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_rcc.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_rcc_ex.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_gpio.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_dma.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_tim.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_tim_ex.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_adc.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_adc_ex.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_iwdg.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_pcd.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_pcd_ex.c"
  "${HAL_DIR}/Src/stm32g0xx_ll_usb.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_pwr.c"
  "${HAL_DIR}/Src/stm32g0xx_hal_pwr_ex.c"
)

set(USB_SOURCES
  "${USB_DIR}/Core/Src/usbd_core.c"
  "${USB_DIR}/Core/Src/usbd_ctlreq.c"
  "${USB_DIR}/Core/Src/usbd_ioreq.c"
  "${USB_DIR}/Class/CDC/Src/usbd_cdc.c"
)

set(COMMON_SOURCES
  common/Src/jpbb_board.c
  common/Src/jpbb_control.c
  common/Src/jpbb_protocol.c
  common/Src/jpbb_usb.c
  common/Src/stm32g0xx_hal_msp.c
  common/Src/stm32g0xx_it.c
  common/Src/usb_device.c
  common/Src/usbd_cdc_if.c
  common/Src/usbd_conf.c
  common/Src/usbd_desc.c
)

add_executable("${KART_STEP}"
  "${STEP_DIR}/main.c"
  ${COMMON_SOURCES}
  ${HAL_SOURCES}
  ${USB_SOURCES}
  "${CMSIS_DIR}/Device/ST/STM32G0xx/Source/Templates/system_stm32g0xx.c"
  "${STARTUP}"
)

target_include_directories("${KART_STEP}" PRIVATE
  common/Inc
  "${HAL_DIR}/Inc"
  "${HAL_DIR}/Inc/Legacy"
  "${CMSIS_DIR}/Include"
  "${CMSIS_DIR}/Device/ST/STM32G0xx/Include"
  "${USB_DIR}/Core/Inc"
  "${USB_DIR}/Class/CDC/Inc"
)

target_compile_definitions("${KART_STEP}" PRIVATE
  STM32G0B1xx
  USE_HAL_DRIVER
)

target_compile_options("${KART_STEP}" PRIVATE
  -mcpu=cortex-m0plus
  -mthumb
  -ffunction-sections
  -fdata-sections
  -fstack-usage
  -Wall
  -Wextra
  -Wshadow
  -Wconversion
  -Wdouble-promotion
  $<$<CONFIG:Debug>:-Og>
  $<$<CONFIG:Release>:-Os>
)

target_link_options("${KART_STEP}" PRIVATE
  -mcpu=cortex-m0plus
  -mthumb
  -T${CMAKE_CURRENT_LIST_DIR}/linker/STM32G0B1CBTX_FLASH.ld
  -Wl,--gc-sections
  -Wl,--print-memory-usage
  -Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/${KART_STEP}.map
  --specs=nano.specs
  --specs=nosys.specs
)

add_custom_command(TARGET "${KART_STEP}" POST_BUILD
  COMMAND ${CMAKE_OBJCOPY} -O ihex
          "$<TARGET_FILE:${KART_STEP}>"
          "${CMAKE_CURRENT_BINARY_DIR}/${KART_STEP}.hex"
  COMMAND ${CMAKE_OBJCOPY} -O binary
          "$<TARGET_FILE:${KART_STEP}>"
          "${CMAKE_CURRENT_BINARY_DIR}/${KART_STEP}.bin"
  COMMAND ${CMAKE_SIZE} "$<TARGET_FILE:${KART_STEP}>"
  VERBATIM
)
