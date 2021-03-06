/**
 * @file small.c
 * @author Matthew Ruffell
 * @date 8 July 2015
 * @short A short vulnerable program to test Avatar
 */

// Include header files

#include "inc/hw_types.h"
#include "inc/hw_memmap.h"
#include "inc/hw_ints.h"
#include "inc/lm3s1968.h"
#include "driverlib/debug.h"
#include "driverlib/sysctl.h"
#include "driverlib/gpio.h"
#include "driverlib/uart.h"
#include "drivers/rit128x96x4.h"
#include <string.h>
#include <stdlib.h>

typedef long int32_t;

#ifdef DEBUGa
void
__error__(char *pcFilename, unsigned long ulLine)
{
}
#endif


// Global Variables


// Functions

char* vulncpy(char* input)
{
	char buffer[20];
    strcpy(buffer, input);
    return buffer;
}


/**
 * Initialises the UART for use
 * @param None
 * @returns None
 */
void uart_initialise (void)
{
	SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOA);
	SysCtlPeripheralEnable(SYSCTL_PERIPH_UART0);

	GPIOPinTypeUART(GPIO_PORTA_BASE, GPIO_PIN_0 | GPIO_PIN_1);

	UARTConfigSetExpClk (UART0_BASE, SysCtlClockGet (), 38400,
			UART_CONFIG_WLEN_8 | UART_CONFIG_STOP_ONE |
			UART_CONFIG_PAR_NONE);

	UARTEnable(UART0_BASE);
}




int main(void)
{
    // Set the clock to run from the crystal at 8Mhz
    SysCtlClockSet (SYSCTL_SYSDIV_10 | SYSCTL_USE_PLL | SYSCTL_OSC_MAIN |
                   SYSCTL_XTAL_8MHZ);

    // Initialise the OLED display.
    RIT128x96x4Init (1000000);

    // Initialise UART
    uart_initialise ();

    long i = 0;

    char string[50] = {0};

	long length = ((char) UARTCharGet (UART0_BASE)) - 48;

	while (i < length)
	{
		string[i] = ((char)UARTCharGet (UART0_BASE));
		i++;
	}
	string[i] = '\0';

	vulncpy (string);

}
