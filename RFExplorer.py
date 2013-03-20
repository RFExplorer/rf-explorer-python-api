import serial
import os
import time
from serial.tools import list_ports
import binascii

GO = '#'+chr(0x04)+'C0'
STOP = '#'+chr(0x04)+'CH'
LCD_OFF = '#'+chr(0x04)+'L0'
LCD_ON = '#'+chr(0x04)+'L1'

#SHUTDOWN DOESN'T WORK RELIABLY
SHUTDOWN = '#'+chr(0x04)+'CS'

#from Thomas at http://stackoverflow.com/questions/12090503/listing-available-com-ports-with-python
#Not sure if this is the best way of doing this.  We want the name to match SiLabs Driver
#to pass to the RFE serial init
def list_serial_ports():
    """
    .. function:: list_serial_ports()

   Lists all of an OS's serial ports

   :rtype: list of strings
   """
    # Windows
    if os.name == 'nt':
        # Scan for available ports.
        available = []
        for i in range(256):
            try:
                s = serial.Serial(i)
                available.append('COM'+str(i + 1))
                s.close()
            except serial.SerialException:
                pass
        return available
    else:
        # Mac / Linux
        return [port[0] for port in list_ports.comports()]     
        
class RFExplorer:
    """Instantiates an RFExplorer instance.

        Must take an integer of the COM port list, not the index.
        For example if the COM port that the RFE is attached to is displayed by
        Windows as COM4, then provide the number 4 to the RFExplorer instance.

        Args:
            port: Integer of the COM port that the RF Explorer is attached to

        Returns:
            ser: A serial.Serial object.
            freq_list: None

        Raises:
            SerialException: could not open port [COMport]: [Error 2] The system cannot find the file specified.
    """
    def __init__(self,port):    
        self.port = port
        ser = serial.Serial(int(port-1))
        ser.baudrate = 2400
        ser.timeout = 5
        self.ser = ser
        self.freq_list = None

    def initialize_RFE_connection(self):
        """
        Starts the RF Explorer sending data.
        Args:
            None
        Returns:
            device_info: a list of the device's info
        Raises:
            ValueError:"RFE returned a value that was not '4L'"
        """
        try:
            s = self.ser.write(GO)
            #assert s == '4L'
        except:
            raise ValueError("RFE returned a value that was not '4L'")
            
        #check if everything is A-OK before collecting data
        response = self.ser.readline().split(':')
        
        if response[0] != '#C2-M':#we know this is NOT the Current_Setup key.
            ready = False
            #keep closing/reopening and flushing com port to get back to square one
            while ready == False:
                self.ser.write(STOP)
                self.ser.close()
                print 'sleeping'
                time.sleep(0.25)
                print 'trying again'
                self.ser.open()
                self.ser.flushInput()
                self.ser.write(GO)
                response = self.ser.readline().split(':')
                if response[0] == '#C':
                    ready = True
        #don't know if the RFE info matters, but can collect it here
        RFE_info = response[1]
        return RFE_info
        
    def parse_C2_F_response(self):  
        """
        Gives Frequency List from a C2 F response from the device
        Args:
            None
        Returns:
            freq_list: a list of the 112 frequencies that are being swept
        Raises:
            NameError: Means that self.ser.readline() is not providing a C2F 
        """        
        #Now that we have the first info line, the next line should be the Current_Config
        request_config = self.ser.readline().split(':')
        if request_config[0] == '#C2-F':# we know this is the Current_Config key
            request_config = request_config[1].split(',')
            initStart_Freq = int(request_config[0])*1000 #MAKE THIS Hz
            initFreq_Step = int(request_config[1]) # in Hz
            initAmp_Top = request_config[2]
            initAmp_Bottom = request_config[3]
            initSweep_Steps = int(request_config[4])
            initExpModuleStatus = request_config[5]
            initCurrentMode = request_config[6]
            initMin_Freq = request_config[7]
            initMax_Freq = request_config[8]
            initMax_Span = request_config[9]
            initResBandWidth = int(request_config[10])
            #now we can do some data collection
            initSpan = initFreq_Step * initSweep_Steps
            initEndFreq = initStart_Freq + initSpan
            initCenterFreq = initStart_Freq + (initSpan/2)
            print 'Span=%s, EndFreq=%s, CFreq=%s, StepFreq=%s' % (initSpan, initEndFreq, initCenterFreq, initFreq_Step)
            freq_list = [str(initStart_Freq)]
            for freq in range(1, int(initSweep_Steps)):
                #add a new list entry which is initFreq_Step greater than the previous list entry
                freq_list.append(str(int(freq_list[freq-1]) + int(initFreq_Step)))
            self.freq_list = freq_list
            return freq_list
        else:
            raise NameError("C2F value is not present in the serial port's queue")
            
    def collect_data(self):
        """
        Args:
            self
        Returns:
            final_results: a list of the 112 data point values to correspond with the freq_list above
        Raises:
            SerialException:None
            Used to break a while loop if all has gone to hell
        """
        first = self.ser.readline()
        if not first.startswith('$S'):
            not_ready = True
            while not_ready == True:
                results = self.ser.readline()
                if results.startswith('$S'):
                    not_ready = False
                elif not results.startswith('#'):
                    break
                    raise serial.SerialException
        else:
            results = first
        #read one line for now
        result = binascii.b2a_qp(results)
        result = "".join(result.splitlines())
        separated = result.split('=')
        final_results = []
        for i in separated:
            if (len(i) == 0) or i.startswith("$"):
                continue
            i = (int(i, 16)/2)*-1#convert to dBm
            final_results.append(i)
        #print 'Value list is %s long' % len(final_results)    
        return final_results
            
    def compile_dictionary(self, values):
        freq_dict = {}
        for indx, freq in enumerate(self.freq_list):
            freq_dict[freq] = values[indx]
        return freq_dict
        
              
    def stop_please(self):
        self.ser.write(STOP)
        time.sleep(0.5)
        self.ser.close()
        time.sleep(0.5)
        self.ser.open()
        time.sleep(0.5)
        self.ser.flushInput()
        time.sleep(0.5)
        self.ser.flush()
        time.sleep(0.5)
        
    def set_sweep_params(self, start_freq, end_freq, amp_top, amp_bottom):
        """
        Args:
            self
            start_freq: 7 digit value in kHz. Can be between 0240000 and 0959888
            end_freq: 7 digit value in kHz. Can be between 0241112 and 0960000
            amp_top: 4 digit value in dBm include the +/- sign. Between -110 and +005  
            amp_bottom: 4 digit value in dBm include the +/- sign. Between -120 and -005 
        Returns:
            boolean: True designates a successful change of parameters
        Raises:
            ValueError: Incorrect Value submitted
            ValueError: Length of Value is not correct
            ValueError: Write to RFE Failed
        """
        if int(start_freq) < 240000 or int(start_freq) > 959888:
            raise ValueError("start_freq not in bounds")
        if int(end_freq) < 241112 or int(end_freq) > 960000:
            raise ValueError("end_freq not in bounds")
        if int(amp_top) < -110 or int(amp_top) > 5:
            raise ValueError("amp_top not in bounds")
        if int(amp_bottom) < -120 or int(amp_bottom) > -5:
            raise ValueError("amp_bottom not in bounds")
        start_freq = str(start_freq)
        end_freq = str(end_freq)
        amp_top = str(amp_top)
        amp_bottom = str(amp_bottom)
        if len(start_freq) < 7:
            sf_0 = 7-len(start_freq) 
            start_freq = ('0'*sf_0) + start_freq
        if len(end_freq) < 7:
            ef_0 = 7-len(end_freq) 
            end_freq = ('0'*sf_0) + end_freq
        if len(amp_top) != 4:
            raise ValueError("length of amp_top is not 4") 
        sweep_params = '#'+chr(0x20)+'C2-F:'+start_freq+','+end_freq+','+amp_top+','+amp_bottom
        try:
            s = self.ser.write(sweep_params)
            return True
        except:
            raise ValueError("write to RFE failed")
                
    def sweep_set_A(self):
        """
        This calls the normal data output that the RF dept likes to see. Imports directly into IAS
        Args:
            self
            filename: the name of the resulting CSV
        Returns:
            boolean: if everything went swimmingly
        Raises:
            ValueError: RFE_connection didn't initialize properly.
                        This means that the length of self.freq_dict is not 112 as it should be
        """
        start = '04500000'
        end = '0512000'
        top = '-010'
        bottom = '-100'
        sweep_settings = self.set_sweep_params(start,end,top,bottom)
        if sweep_settings == True:
            freq_list = self.parse_C2_F_response()
            if len(freq_list) != 112:
                raise ValueError("RFE_connection didn't initialize properly")
        else:    
            raise ValueError("RFE didn't take the sweep_settings")
#       #RF guys want this to be 3 minutes to sweep for 2-way radios.  This 30 sec time is used for debugging
        stop_sweep = time.time() + 30
        #collect data points, convert them to int and save the highest data points
        final_result = self.collect_data()
        while time.time() < stop_sweep:
            one_result = self.collect_data()
            if len(final_result) == len(one_result):
                for i, v in enumerate(final_result):
                    if one_result[i] > v:
                        final_result[i] = one_result[i]
        first_dict = self.compile_dictionary(final_result)
        return first_dict
        
    def quick_sweep(self, start,end,stop_sweep):
        """ Set the sweep settings and gather data for a specified time
            Args:
                start: 7 digit entry of starting frequency for the sweep 
                end: 7 digit entry of end frequency for the sweep
                stop_sweep: length of time in seconds for the sweep repeat and compare
            Returns:
                value_dictionary to compare with other sweep data
        """
        self.stop_please()
        top = '-010'
        bottom = '-100'
        sweep_settings = self.set_sweep_params(start,end,top,bottom)
        if sweep_settings == True:
            freq_list = self.parse_C2_F_response()
            if len(freq_list) != 112:
                raise ValueError("RFE_connection didn't initialize properly")
        else:    
            raise ValueError("RFE didn't take the sweep_settings")
        final_result = self.collect_data()
        stop_sweep = time.time() + stop_sweep
        while time.time() < stop_sweep:
            one_result = self.collect_data()
            if len(final_result) == len(one_result):
                for i, v in enumerate(final_result):
                    if one_result[i] > v:
                        final_result[i] = one_result[i]
        first_dict = self.compile_dictionary(final_result)
        return first_dict
        
    def make_csv(self, filename, freq_dict):
        """
        creates the final CSV file by converting all Hz values to MHz
        sorts the results dictionary and writes the file.
        Args: 
            filename: the name of the file that will be saved to the working directory
        Returns: 
            file: CSV file with filename of filename arg formatted correctly
        Raises:
            
        """
        if filename.endswith('.csv'):
            file = filename
        else:
            file = str(filename)+'.csv'
        fout = open(file, 'w')
        freq_dict = sorted(freq_dict.items())
        for i, v in freq_dict:
            x = ''
            for j in str(i)[0:3]:
                x += j
            x+='.'
            for j in str(i)[4:7]:
                x += j
            fout.write(str(x)+','+str(v)+'\n')
        fout.close()
        return True
        