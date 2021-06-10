#!/usr/bin/python
#Assignment 4

import threading
import RPi.GPIO as GPIO
import time
import requests
import json
from datetime import date
import datetime
import Freenove_DHT as DHT
from PCF8574 import PCF8574_GPIO
from Adafruit_LCD1602 import Adafruit_CharLCD

##Pin numbering declarations (setup channel mode of the Pi to Board values)
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
##Set GPIO pins (for inputs and outputs) and all setupts needed based on assignment description
DHT_PIN = 17
LIGHT_PIN = 26
BTN_D = 12
BTN_R = 21
BTN_B = 20
BTN_S = 16
LED_R = 23
LED_G = 25
LED_B = 24

GPIO.setup(21,GPIO.IN, pull_up_down=GPIO.PUD_UP)    #red button
GPIO.setup(20,GPIO.IN, pull_up_down=GPIO.PUD_UP)    #blue button
GPIO.setup(16,GPIO.IN, pull_up_down=GPIO.PUD_UP)    #green button
GPIO.setup(12,GPIO.IN, pull_up_down=GPIO.PUD_UP)    #door button
GPIO.setup(LIGHT_PIN, GPIO.IN)  # set sensorPin to INPUT mode

GPIO.setup(23,GPIO.OUT)                              #red LED
GPIO.setup(24,GPIO.OUT)                             #blue LED
GPIO.setup(25,GPIO.OUT)                              #green LED


#global variables
dht = None #DHT object
temp_lock = threading.Lock() #temp mutex
lcd_lock = threading.Lock() #lcd mutex
door = 1    #0=open, 1=closed
temp = 0
set_temp = 0
temp_set_flag = 0 #set if temp is changed by user
hvac = 0 #0 = off, 1=AC, 2=Heater
lights = 0 #lcd lights indicator, 0=off, 1=on
motion = 0 #lights signal to turn on, 0=off, 1=on

#Configure LCD
PCF8574_address = 0x27 # I2C address of the PCF8574 chip.
PCF8574A_address = 0x3F # I2C address of the PCF8574A chip.
try:
	mcp = PCF8574_GPIO(PCF8574_address)
except:
	try:
		mcp = PCF8574_GPIO(PCF8574A_address)
	except:
		print ('I2C Address Error !')
		exit(1)
# Create LCD, passing in MCP GPIO adapter.
lcd = Adafruit_CharLCD(pin_rs=0, pin_e=2, pins_db=[4,5,6,7], GPIO=mcp)
mcp.output(3,1)	
lcd.begin(16,2)	#set number of LCD lines

#CIMIS app key
app_key = 'c0a7eebb-598f-4558-a7fa-1d9d35668784'
station = 75 #irvine CIMIS station
#get humidity from CIMIS website
def get_hum():
    today = date.today()
    value = None
    while (value==None): #if current humidity not available, finds last registered humidity
        try:
            response = requests.get('http://et.water.ca.gov/api/data?appKey='+app_key+'&targets='+str(station)+'&startDate='+str(today)+'&endDate='+str(today)+'&dataItems=day-rel-hum-avg&unitOfMeasure=M')
        except requests.exceptions.RequestException as e:
            continue
        yesterday = today-datetime.timedelta(days=1)
        today = yesterday
        data = json.loads(response.text)
        try:
            value = data["Data"]["Providers"][0]["Records"][0]["DayRelHumAvg"]["Value"]
        except:
            continue
    print("Humidity = "+value+"\n")
    return value

## Event listener (Tell GPIO library to look out for an event on each pushbutton and pass handle function)
## fucntion to be run for each pushbutton detection ##
def button_listener():
	GPIO.add_event_detect(BTN_R, GPIO.FALLING, callback=red, bouncetime=1000)
	GPIO.add_event_detect(BTN_B, GPIO.FALLING, callback=blue, bouncetime=1000)
	GPIO.add_event_detect(BTN_S, GPIO.FALLING, callback=reset, bouncetime=1000)
	GPIO.add_event_detect(BTN_D, GPIO.FALLING, callback=set_door, bouncetime=3000)
	GPIO.add_event_detect(LIGHT_PIN, GPIO.FALLING, callback =green, bouncetime = 1000)

#button and pir handler functions
#change door open/closed
def set_door(pin):
    global lcd, door, hvac, temp_set_flag, set_temp
    if (door == 1):
        door = 0    #open door
        lcd_lock.acquire()
        lcd.clear()
        lcd.setCursor(0,0)
        lcd.message('Door/Window Open')
        if (hvac != 0):
            lcd.setCursor(0,1)
            lcd.message('HVAC Halted')
            hvac = 0
            set_hvac()
        #reset set temp and flag
        temp_lock.acquire()
        set_temp = temp
        temp_set_flag = 0
        temp_lock.release()
        time.sleep(3.0)
        lcd.clear()
        lcd_lock.release()
        lcd_refresh()
        return
    else:
        door = 1 #close door
        lcd_lock.acquire()
        lcd.clear()
        lcd.setCursor(0,0)
        lcd.message('Door/Window')
        lcd.setCursor(0,1)
        lcd.message('Closed')
        #reset set temp and flag
        temp_lock.acquire()
        set_temp = temp
        temp_set_flag = 0
        temp_lock.release()
        time.sleep(3.0)
        lcd.clear()
        lcd_lock.release()
        set_hvac()
        lcd_refresh()
        return
#update LCD hud 
def lcd_refresh():
    lcd_lock.acquire()
    lcd.clear()
    lcd.setCursor(0,0)
    lcd.message(str(temp)+'/'+str(set_temp))
    lcd.setCursor(10,0)
    if (door == 1):
        lcd.message('D:SAFE')
    else:
        lcd.message('D:OPEN')
    lcd.setCursor(0,1)
    if (hvac == 0): 
        lcd.message("H:OFF")
    elif (hvac == 1):
        lcd.message("H:AC")
    else:
        lcd.message("H:HEAT")
    lcd.setCursor(10,1)
    if (lights == 0):
        lcd.message('L:OFF')
    else:
        lcd.message('L:ON')
    lcd_lock.release()

#turn on leds for ac and heater 
def set_hvac():
    #if hvac off, turn off leds
    if (hvac == 0):
        GPIO.output(LED_B, False)
        GPIO.output(LED_R, False)
    #if ac set, turn on ac, turn off heater
    elif (hvac == 1):
        GPIO.output(LED_B, True)
        GPIO.output(LED_R, False)
    #if heater set, turn on heater, turn off ac
    elif (hvac ==2):
        GPIO.output(LED_B, False)
        GPIO.output(LED_R, True)

#reset leds and default values
def reset(pin):
    global door, temp, set_temp, temp_set_flag, hvac, lights, motion
    lcd_lock.acquire()
    temp_lock.acquire()
    GPIO.output(LED_R, False)
    GPIO.output(LED_G, False)
    GPIO.output(LED_B, False)
    door = 1    
    temp = 0
    set_temp = 0
    temp_set_flag = 0 
    hvac = 0 
    lights = 0
    motion = 0
    lcd.clear()
    lcd.setCursor(0,0)
    lcd.message('HVAC RESET')
    time.sleep(1)
    lcd.clear()
    temp_lock.release()
    lcd_lock.release()

#increase set temperature, turn on heater if 3 degrees above temp    
def red(pin):	#heater
    global lcd, temp, set_temp, temp_set_flag, hvac
    #block changes if door is open
    if (door == 0):
        lcd_lock.acquire()
        lcd.clear()
        lcd.setCursor(0,0)
        lcd.message('Door Open')
        lcd.setCursor(0,1)
        lcd.message('HVAC Off')
        time.sleep(1)
        lcd_lock.release()
        lcd_refresh()
        return
    #once flag is set, set_temp no longer updates to temp
    if (temp_set_flag==0):
        temp_set_flag = 1
    GPIO.output(LED_R, True)
    #update set temp
    if (set_temp<85):
        temp_lock.acquire()
        set_temp+=1
        time.sleep(.5)
        temp_lock.release()
        print('set temp:'+str(set_temp)+'\n')
    #if temp<set_temp+3, turn on heater 
    if (temp<=set_temp-3 and hvac!=2):
        hvac = 2
        lcd_lock.acquire()
        lcd.clear()
        lcd.setCursor(0,0)
        lcd.message('Heater On')
        time.sleep(3)
        lcd_lock.release()
    GPIO.output(LED_R, False)
    set_hvac()
    lcd_refresh()

#decrease set temperature, turn on AC if 3 deg below temp
def blue(pin):	#AC
    global lcd, temp, set_temp, temp_set_flag, hvac
    #block changes if door is open
    if (door == 0):
        lcd_lock.acquire()
        lcd.clear()
        lcd.setCursor(0,0)
        lcd.message('Door Open')
        lcd.setCursor(0,1)
        lcd.message('HVAC Off')
        time.sleep(1)
        lcd_lock.release()
        lcd_refresh()
        return
    #once flag is set, set_temp no longer updates to temp
    if (temp_set_flag==0):
        temp_set_flag = 1
    GPIO.output(LED_B, True)
    #update set temp
    if (set_temp>65):
        temp_lock.acquire()
        set_temp-=1
        time.sleep(.5) #led time
        temp_lock.release()
        print('set temp:'+str(set_temp)+'\n')
    #if temp<set_temp+3, turn on heater 
    if (temp>=set_temp+3 and hvac!=1):
        hvac = 1
        lcd_lock.acquire()
        lcd.clear()
        lcd.setCursor(0,0)
        lcd.message('AC ON')
        time.sleep(3)
        lcd_lock.release()
    GPIO.output(LED_B, False)
    set_hvac()
    lcd_refresh()

#motion detected light
def green(pin):
    global lights, motion
    GPIO.output(LED_G,True)
    print ('led turned on <<<')
    motion = 1
    lights = 1

#turn on light when movement detected
def light_loop():
    global lights, motion
    #polling loop checks if motion signal is set
    while True:
        if (motion == 1):
            motion = 0
            time.sleep(10)  #light turns off if no motion detected during this period, else renews
            if (motion == 0):
                GPIO.output(LED_G, False)
                lights = 0

#button handling thread
def button_loop():
    print('Button thread started')
    button_listener()
    while True:
        time.sleep(1e6)

#temperature updating thread
def dht_loop():
    global temp, dht, set_temp, temp_set_flag
    print('DHT thread started')
    hum = get_hum()
    count = 0
    vals = [0,0,0]
    while(True):
        chk = dht.readDHT11()
        if (chk is dht.DHTLIB_OK): #read DHT11 and get a return value. Then determine whether data read is normal according to the return value.
            #convert to fahrenheit
            t = dht.temperature*9/5+32
            vals[count%3] = t
            count+=1
            #print("Temperature received: %.2f \n"%(t))
        if (count >= 3):
            temp = int(sum(vals)/3+.05*float(hum))
            if (temp_set_flag == 0):
                temp_lock.acquire()
                set_temp = temp
                temp_lock.release()
            print("Temperature : %d \n"%(temp))
        lcd_refresh() #update lcd with new temp every second
        time.sleep(1)   #repeat every second

def destroy():
    GPIO.cleanup()      # Release GPIO resource
    sys.exit()

if __name__ == '__main__':     # Program entrance
    print('Program is starting...')
    #initialize temps
    dht = DHT.DHT(DHT_PIN) #create a DHT class object
    dht.readDHT11()
    temp = int(dht.temperature*9/5+32)
    set_temp = temp
    print('tempflag ='+str(temp_set_flag)+', door='+str(door)+'\n')
    time.sleep(.5)
    lcd_refresh()
    button_thread = threading.Thread(target=button_loop)
    dht_thread = threading.Thread(target=dht_loop)
    light_thread = threading.Thread(target=light_loop)
    button_thread.daemon = True
    dht_thread.daemon = True
    light_thread.daemon = True
    try:
        button_thread.start()
        dht_thread.start()
        light_thread.start()
    except KeyboardInterrupt:
        destroy()
    button_thread.join()
    dht_thread.join()
    light_thread.join()