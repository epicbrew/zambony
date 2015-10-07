from CDROM import *
import os
import os.path
from Tkinter import *
from tkFileDialog import askopenfilename, askdirectory
from tkMessageBox import showinfo, showerror
from subprocess import *
from tempfile import mkdtemp
from fcntl import ioctl


drive_status = {CDS_NO_DISC: "No disk",
                CDS_TRAY_OPEN: "No disk",
                CDS_DRIVE_NOT_READY: "Loading",
                CDS_DISC_OK: "Ready"}


class FileInfo:
    def __init__(self, path):
        self.path = path

        if os.path.isdir(path):
            print 'getting size of:', path
            du = Popen(['du', '-s', path], stdout=PIPE)
            stdoutdata = du.communicate()[0]
            size_str = stdoutdata.split()[0]
            self.size = int(size_str)
        else:
            file_info = os.stat(path)
            self.size = file_info.st_size

        if self.size < (1024 * 1024):
            kb = float(self.size) / 1024.0
            self.size_text = "%.1f KB" % kb
        else:
            mb = float(self.size) / (1024.0 * 1024.0)
            self.size_text = "%.1f MB" % mb

    @property
    def name(self):
        #basename = self.path.split(os.sep)[-1]
        basename = os.path.basename(self.path)
        if os.path.isdir(self.path):
            basename += '/'

        return basename

    def __str__(self):
        return '%s (%s)' % (self.name, self.size_text)


class StatusWindow(Toplevel):
    def __init__(self, file):
        Toplevel.__init__(self)
        self.file = file

        self.sb = Scrollbar(self, orient=VERTICAL)
        self.sb.pack(side=RIGHT, fill=Y)
        self.txt = Text(self, wrap=WORD, yscrollcommand=self.sb.set)
        self.sb.config(command=self.txt.yview)
        self.txt.pack(fill=BOTH, expand=TRUE)

        self.tk.createfilehandler(file,
                                  READABLE, self.data_callback)


    def data_callback(self, file, mask):
        text_data = os.read(file.fileno(), 512)

        if len(text_data):
#            for c in text_data:
#                if c == '\r':
#                    print 'found carriage return'
#                    index = self.txt.index('linestart')
#                    print 'got index', index
#                    self.txt.delete(index, END)
#                else:
#                    self.txt.insert(END, c)
            self.txt.insert(END, text_data)
            self.txt.yview(END)
        else:
            self.tk.deletefilehandler(file)


class DeviceInfo:
    cdr = False
    dvdr = False
    bluray = False


    def __init__(self, name, speed):
        self.name = name
        self.speed = speed


    @property
    def capabilities(self):
        caps = ""
        if not self.cdr and not self.dvdr:
            caps += "Not Writable"
        else:
            if self.cdr:
                caps += " CD-R,"
            if self.dvdr:
                caps += " DVD-R,"

            caps += " %dx" % self.speed

        return caps

    def __str__(self):
        return self.name


class Zambony:
    device_status_alarm = None

    def __init__(self):
        self.devices = []
        self.burn_files = []

        self.get_device_info()

        dummy = DeviceInfo('/dev/dummy', 2)
        dummy.cdr = True
        dummy.dvdr = True
        self.devices.append(dummy)

        self.create_gui()

        if len(self.devices) > 0:
            self.start_device_monitoring()
        else:
            showerror(title='Error',
                    message='No CD/DVD burning devices found.\n'+
                            'Check that a write capable device exists\n'+
                            'and that you have read/write permissions.',
                    parent=self.root)


    def run(self):
        self.root.mainloop()
        self.stop_device_monitoring()


    def get_device_info(self):
        f = open('/proc/sys/dev/cdrom/info')
        lines = f.readlines()
        f.close()

        dev_dict = {}
        for line in lines[1:]:
            words = line.rstrip().split(':')
            if len(words) > 1:
                key, vals = words[0], words[1]
                dev_dict[key] = []
                for val in vals.split():
                    dev_dict[key].append(val)

        for i in range(0, len(dev_dict['drive name'])):
            name = '/dev/' + dev_dict['drive name'][i]
            speed = int(dev_dict['drive speed'][i])
            di = DeviceInfo(name, speed)
            di.cdr = bool(dev_dict['Can write CD-R'][i])
            di.dvd = bool(dev_dict['Can write DVD-R'][i])

            if di.cdr or di.dvdr:
                self.devices.append(di)

        for dev in self.devices:
            print dev.name, dev.capabilities


    def add_device_panel(self):
        frame = Frame(self.gui)
        frame.pack(side=TOP, fill=X)
        Label(frame, text="Recording Device:").pack(side=LEFT, anchor=W)

        self.device_label = StringVar()
        self.device_status = StringVar()
        self.device_var = StringVar()

        devlabel = Label(frame, textvar=self.device_label)
        statuslabel = Label(frame, textvar=self.device_status)

        items = tuple([ d.name for d in self.devices ])
        if len(items):
            self.device_var.set(self.devices[0].name)
            self.device_label.set(self.devices[0].capabilities)

        mb = OptionMenu(frame, self.device_var, *items)
        mb.pack(side=LEFT)
        devlabel.pack(side=LEFT)
        statuslabel.pack(side=RIGHT)
        Label(frame, text="Drive Status:").pack(side=RIGHT)

        self.device_var.trace('w', self.device_changed)


    def start_device_monitoring(self):
        self.device_status_alarm = self.gui.after(500, self.get_device_status)


    def stop_device_monitoring(self):
        if self.device_status_alarm:
            self.gui.after_cancel(self.device_status_alarm)
            self.device_status_alarm = None


    def device_changed(self, *args):
        for dev in self.devices:
            if dev.name == self.device_var.get():
                self.device_label.set(dev.capabilities)


    def get_device_status(self):
        try:
            fd = os.open(self.device_var.get(), os.O_NONBLOCK | os.O_RDONLY)
            status = ioctl(fd, CDROM_DRIVE_STATUS)
            os.close(fd)
        except:
            self.device_status.set('Error')
        else:
            self.device_status.set(drive_status[status])

        self.device_status_alarm = self.gui.after(1000, self.get_device_status)


    def create_gui(self):
        self.root = Tk()
        self.root.title("Zambony")
        self.create_images()
        self.gui = Frame(self.root)
        self.gui.pack(fill=BOTH, expand=TRUE)
        self.add_device_panel()
        self.add_controls()
        self.add_file_frame()

    def _control_button(self, text, image, command, side=LEFT):
        b = Button(self.control_frame, text=text)
        b.config(command=command)
        b.config(compound=LEFT, image=image)

        if side == LEFT:
            b.pack(side=LEFT, anchor=W)
        else:
            b.pack(side=RIGHT, anchor=E)


    def add_controls(self):
        self.control_frame = Frame(self.gui)
        self.control_frame.pack(side=BOTTOM, fill=X, anchor=S)

        self._control_button("Add File", self.add_file_img, self.add_file)
        self._control_button("Add Directory", self.add_dir_img, self.add_dir)
        self._control_button("Remove Selected Item", self.remove_img, self.remove_item)
        self._control_button("Burn", self.burn_img, self.burn, side=RIGHT)


    def add_file_frame(self):
        self.file_area = Frame(self.gui)
        self.file_area.pack(side=TOP, fill=BOTH, expand=TRUE)
        Label(self.file_area, text="Files on CD/DVD:").pack(side=TOP, anchor=NW)

        yscrollbar = Scrollbar(self.file_area, orient=VERTICAL)
        yscrollbar.pack(side=RIGHT, fill=Y)

        self.filelistbox = Listbox(self.file_area, yscrollcommand=yscrollbar.set)
        yscrollbar.config(command=self.filelistbox.yview)
#        xscrollbar = Scrollbar(self.file_frame, orient=HORIZONTAL)
#        xscrollbar.config(command=listbox.xview)
#        xscrollbar.pack(side=BOTTOM, fill=X)

        self.filelistbox.pack(fill=BOTH, expand=TRUE, padx=5)


    def add_file(self):
        filename = askopenfilename(title='Select File')
        if filename:
            f_info = FileInfo(filename)
            self.burn_files.append(f_info)
            self.filelistbox.insert(END, f_info)


    def add_dir(self):
        dirname = askdirectory(title='Select Directory', mustexist=True)
        if dirname:
            d_info = FileInfo(dirname)
            self.burn_files.append(d_info)
            self.filelistbox.insert(END, d_info)


    def remove_item(self):
        if self.filelistbox.size():
            i = self.filelistbox.index(ACTIVE)
            print 'Removing item with index: %d' % i
            self.filelistbox.delete(i)
            self.burn_files.pop(i)


    def burn(self):
        self.stop_device_monitoring()
        self.device_status.set("Recording")

        tempdir = mkdtemp(prefix='zambony.', dir='/var/tmp')
        
        for f in self.burn_files:
            print f.path
            print f.path, os.path.join(tempdir,f.name)
            os.symlink(f.path, 
                       os.path.join(tempdir,os.path.basename(f.path)))

        dev = "dev=%s" % self.device_var.get()
        mkisofs_cmd = ['mkisofs', '-J', '-r', '-follow-links', tempdir]
        #cdrecord_cmd = ['cdrecord', '-v', '-eject', '-dummy', 'driveropts=burnfree',
        cdrecord_cmd = ['cdrecord', '-v', '-eject', 'driveropts=burnfree',
                                    dev, '-data', '-']

        self.mkisofs = Popen(mkisofs_cmd, stdout=PIPE)
        self.cdrecord = Popen(cdrecord_cmd, stdin=self.mkisofs.stdout,
                                            stdout=PIPE, stderr=STDOUT)

        sw = StatusWindow(self.cdrecord.stdout)
        self.gui.after(250, self.check_status)


    def check_status(self):
        if not self.cdrecord.poll() is None:
            print "Reaping processes"
            self.mkisofs.wait()
            self.cdrecord.wait()
            print "Processes finished!"

            self.start_device_monitoring()
        else:
            self.gui.after(250, self.check_status)

        
    def create_images(self):
        self.burn_img = PhotoImage(format='gif',data=
             'R0lGODlhGAAYAPcAAP4RA/8ZAP8pAP82AP84Af9DAf9OAv9EC/9TAv9dAv9Z'
            +'Cf9HFP9cHf9kAf9sAP9uC/9zAf97Af91C/54D/5oGP1wE/9zHP5OJv5SKu1O'
            +'Nf9vIv9lKO50JP9xIf54NfJXWOB+V/+DA/+JA/6BDP+KD/+QBv+TDf+CFP6X'
            +'Ev+cFP+QGvWYHP+aH/+yDf+nE/+oH/+1HtuRPP+EI/aMKfyZIf+WLv+cLP6P'
            +'OvCSNPGeMf+SPP+lK/+5I/+jNP+xN/+3PP/dA/7HH/7UKv/RP//dOP/tL//+'
            +'K//pOv/+M//8PP6aRv6HW/6dU/+tRf+lTf6rTv+xRf+1TP6lVv+uVf66U/67'
            +'XP6ab8Onf/6tbf6wYf/WRP/IVP7CW//vRP/vSP/+RP/wTP//Sf/jVf7mXP/+'
            +'U///W/7AZ//DaP7cZP/Kff/nY///Zf/+av/1d35gsSo13xg76gVO9xJW9zla'
            +'7gx1/R95/Cls+Tll9zls9Sh5+Dh6+lBS21Fz7kBj8Wlz7Kt1jaRgrZZ4wC+F'
            +'4iaB7SmG+CKJ+TCK+yCT/i6T/Tqc/Sih/jCm/j+j/jCo/kuB7U2f/Faf/kiv'
            +'/lKi/lmi/Uqz/k66/lKx/lK8/l+8/me0/m+2/me//nK/9nW//n64+17C/mzD'
            +'/m3J/nzK/qiWmYaAtaqRqZmkuKy5tv7Ug//9jf/qkIfH/ILO/oDS/pPX/pjZ'
            +'/qDe/qPg/f/uwQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAACH5BAEAALMALAAAAAAYABgAAAj+AGcJHDjQCsGD'
            +'CBMuOZCwYcIDBZg4nDjLgwEDUig2NNMAgQIqGhP2KFDAgY+QB890IICgRI00'
            +'KAdOQZAgwogTTgZOyKJRCQQHDSBEsDFQhoQqE1GRgNBgBAQRIAXKQBBiYhQH'
            +'EVJIiBCBoISgPRzqcNACSAQHLAZC2YDFRIQmDTuQLSICAo1ZTWyEuCCriggu'
            +'DTcUeCHGRQQIiBsYuJFqS4gdDTEIOHFElQkHCQwkYACGjZgQSBN+CAABzBct'
            +'MhI8+HEkDJkuKp4k9AMIwIIkRsq0GaKmDBLfRCaA8HRwzhs+GQYESUIGiWsy'
            +'a8gYgTHhj55VAy0ZstMnEAUNXsh3hCnzxcgaNCgicNgjB9IrgaAUMcqDp1QF'
            +'C1XEjOEhBAaCpm7AEQcirAwUSiN01PGIKTMkkABiIWCGAyl3xEEHJgeBQkkk'
            +'lVjCySlX5EDDCjGM4sgkkmTSiUOfhHLJIocQMogghSSyiSuxaARLK6KAkokm'
            +'nYjiUEAAOw==')

        self.add_file_img = PhotoImage(format='gif',data=
              'R0lGODlhGAAYAPcAAAtrCA1vCw9vCxx1GhyAEB2DEiCHEiOLEiOMEiaOEjKY'
            +'HjmoHDuqHDyrHDusHT6tHD+vHCmDIDSNJzyeJDWQKDiTKDuWKT6bKUKuG020'
            +'G0GeK0q+IUy+IVO7LFLCHlPDHlfFH1fGH17DGVjGG1rGG1vHG1jGH1rGH13J'
            +'G1/JG1vIH13IH13JH17JH17LH2TIG2DLH2HMHGLNH2PNH2TNHWXNH2XOH2bO'
            +'HmjLG23PGWjPHW3RGG/UGWjQHmnQHmvRHm7THG3RHm3THm7THnDTFHfaFHXY'
            +'F3fYF3/eEnnaF3PSGXDTG3HUGHDVGHbXGHDTHHHVHHPVHHPWHHTWHHbYHHjZ'
            +'G3nZG3vbG3zbG37cGX7cG3jZHEvCIk3AIU/AIU/CIU3DIlDCIVPDIVXDIVXF'
            +'IVfBMXjORnzLXIHeGYPgGYTgGYbdUpztT57uT5/uT4jgUongUoviUo3jUori'
            +'VY/jVJvrUZroU5/tVaPvTKLwTqf0T6XyU6LwVYTQboTRbobQbofSbozVb4jS'
            +'cqDlbqbqbarub6rwbqzwbr3/bKbscKjscK/ycs7/igAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAACH5BAEAAI0ALAAAAAAYABgAAAj+ABsJHChwQocy'
            +'CMt0mECwocNGEw4xmshoEcOHGBUYQsIRCREFGDMWUkNSjRKQIR0qUEQyDZoc'
            +'KFMSVJDIZRYsOGLKFKiAkBYsV6q80LlTwSArW6hMEUF04ISnUKEOoiIFyhMR'
            +'CLJq1aoBEZ48btqwqWOnidUhQXTEoCMnDpw3a+YouKCnSJIjTpg04bFkyA8f'
            +'PW7QiJECRQkSI04ksLDHiNIoUIAI+RvYxgwYLlisUHHChJcDFfgwgQwkCOUb'
            +'NWTAaMFChYoQJkCQ8WKAwp0daE/PUM2as4nYZMR88FJAgpkMyJNnONP7BAYM'
            +'ypFjIBBhgPXrAwCc8W0CA4Dv4MFTYxxwxkQIMmO87yQ4IFDwDx4gAFg/cAAg'
            +'+GG+PJhPv9GAP/l54UUD/NE3gB8CdsEBAwWuN0AfCm6wwQIN7jSAIGCAwQUX'
            +'DlQok3UCCBBAAN9hFBAAOw==')

        self.add_dir_img = PhotoImage(format='gif',data=
             'R0lGODlhGAAYAPfTACd5Hy1+HhdsIhxwISF0IDODHDqJG0COGUyYF0aTGFac'
            +'E1GcFlagFVqjFFasHGClGGqvHXW4Ine8IHi8IlzBDmfGEnHHF3XCHGjjDp7t'
            +'H4DDJ4LIIYvMLIrTIIzWIJncJZbWMaDfNqjnOrfgMdz5Ps/tQsvpRNPwQdTy'
            +'QdTwStv2T9/5Vef9VuL6WSd2xyp5yS18yzGAzjaE0TqI1T+M2EOQ20iU3kyY'
            +'4lCc5VSg6Fij6lum7F6p7l+q7mCq7mGr7mOs72Wu72au72ev72a68Gy+8WS6'
            +'/Wm+/2m//2q+/mzD/3PC8nnG9HDC/3HG/3TG/3fG/3LI/3TK/3XL/3rK/33K'
            +'/3zR/37R/4SEioWFi4aGjIeHjYmIjoqJj4uLkY2Mko6Nk5CPlZGQlpKRl5ST'
            +'mZWUmpeVm5iXnZmYnpuZn5yaoJ2boZ6corCvtIHO/43R9oHS/4fS/4DU/4fW'
            +'/4zS/47T/4ba/47a/5DS95PU95TU95bV95bW95nW95bW+JLW/5TX/5nX+JvX'
            +'+JHY/5XY/5bb/5fb/5Te/5zY+J7Z+J7Z+Z/a+J/a+Zvc/5rd/5ve/57d/5ze'
            +'/6Da+KDa+aHb+aHe/6Lf/6Tf/6Xf/5ri/5vi/6Xg/6Hl/6Ll/6Dm/6Hm/6Xl'
            +'/6fl/6nm/6vn/6zn/63n/67n/6bo/6fo/6bp/67o/6/o/67v/67w/7Ty/7Xy'
            +'/7by/7fy/7f1/7jz/7rz/7vz/7zz/7r5/777/8TDx9rZ29za3d3b3t7d38j/'
            +'/+Hg4uTj5efm6Orp6u3s7e7t7vDv8fDw8PHx8fPy8/X19fb19vf39/j3+Pn4'
            +'+fn5+fv7/Pz7/Pz8/P7+/v///wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAACH5BAEAANQAIf8LSUNDUkdCRzEwMTL/AAAMSExp'
            +'bm8CEAAAbW50clJHQiBYWVogB84AAgAJAAYAMQAAYWNzcE1TRlQAAAAASUVD'
            +'IHNSR0IAAAAAAAAAAAAAAAAAAPbWAAEAAAAA0y1IUCAgAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAARY3BydAAAAVAA'
            +'AAAzZGVzYwAAAYQAAABsd3RwdAAAAfAAAAAUYmtwdAAAAgQAAAAUclhZWgAA'
            +'AhgAAAAUZ1hZWgAAAiwAAAAUYlhZWgAAAkAAAAAUZG1uZAAAAlQAAABwZG1k'
            +'ZAAAAsQAAACIdnVlZAAAA0wAAACGdmll/3cAAAPUAAAAJGx1bWkAAAP4AAAA'
            +'FG1lYXMAAAQMAAAAJHRlY2gAAAQwAAAADHJUUkMAAAQ8AAAIDGdUUkMAAAQ8'
            +'AAAIDGJUUkMAAAQ8AAAIDHRleHQAAAAAQ29weXJpZ2h0IChjKSAxOTk4IEhl'
            +'d2xldHQtUGFja2FyZCBDb21wYW55AABkZXNjAAAAAAAAABJzUkdCIElFQzYx'
            +'OTY2LTIuMQAAAAAAAAAAAAAAEnNSR0IgSUVDNjE5NjYtMi4xAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABYWVog'
            +'AAAAAAAA81EAAf8AAAABFsxYWVogAAAAAAAAAAAAAAAAAAAAAFhZWiAAAAAA'
            +'AABvogAAOPUAAAOQWFlaIAAAAAAAAGKZAAC3hQAAGNpYWVogAAAAAAAAJKAA'
            +'AA+EAAC2z2Rlc2MAAAAAAAAAFklFQyBodHRwOi8vd3d3LmllYy5jaAAAAAAA'
            +'AAAAAAAAFklFQyBodHRwOi8vd3d3LmllYy5jaAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABkZXNjAAAAAAAAAC5JRUMg'
            +'NjE5NjYtMi4xIERlZmF1bHQgUkdCIGNvbG91ciBzcGFjZSAtIHNSR0L/AAAA'
            +'AAAAAAAAAAAuSUVDIDYxOTY2LTIuMSBEZWZhdWx0IFJHQiBjb2xvdXIgc3Bh'
            +'Y2UgLSBzUkdCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGRlc2MAAAAAAAAALFJl'
            +'ZmVyZW5jZSBWaWV3aW5nIENvbmRpdGlvbiBpbiBJRUM2MTk2Ni0yLjEAAAAA'
            +'AAAAAAAAACxSZWZlcmVuY2UgVmlld2luZyBDb25kaXRpb24gaW4gSUVDNjE5'
            +'NjYtMi4xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB2aWV3AAAAAAATpP4A'
            +'FF8uABDPFAAD7cwABBMLAANcngAAAAFYWVog/wAAAAAATAlWAFAAAABXH+dt'
            +'ZWFzAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAACjwAAAAJzaWcgAAAAAENS'
            +'VCBjdXJ2AAAAAAAABAAAAAAFAAoADwAUABkAHgAjACgALQAyADcAOwBAAEUA'
            +'SgBPAFQAWQBeAGMAaABtAHIAdwB8AIEAhgCLAJAAlQCaAJ8ApACpAK4AsgC3'
            +'ALwAwQDGAMsA0ADVANsA4ADlAOsA8AD2APsBAQEHAQ0BEwEZAR8BJQErATIB'
            +'OAE+AUUBTAFSAVkBYAFnAW4BdQF8AYMBiwGSAZoBoQGpAbEBuQHBAckB0QHZ'
            +'AeEB6QHyAfoCAwIMAv8UAh0CJgIvAjgCQQJLAlQCXQJnAnECegKEAo4CmAKi'
            +'AqwCtgLBAssC1QLgAusC9QMAAwsDFgMhAy0DOANDA08DWgNmA3IDfgOKA5YD'
            +'ogOuA7oDxwPTA+AD7AP5BAYEEwQgBC0EOwRIBFUEYwRxBH4EjASaBKgEtgTE'
            +'BNME4QTwBP4FDQUcBSsFOgVJBVgFZwV3BYYFlgWmBbUFxQXVBeUF9gYGBhYG'
            +'JwY3BkgGWQZqBnsGjAadBq8GwAbRBuMG9QcHBxkHKwc9B08HYQd0B4YHmQes'
            +'B78H0gflB/gICwgfCDIIRghaCG4IggiWCKoIvgjSCOcI+wkQCSUJOglPCWT/'
            +'CXkJjwmkCboJzwnlCfsKEQonCj0KVApqCoEKmAquCsUK3ArzCwsLIgs5C1EL'
            +'aQuAC5gLsAvIC+EL+QwSDCoMQwxcDHUMjgynDMAM2QzzDQ0NJg1ADVoNdA2O'
            +'DakNww3eDfgOEw4uDkkOZA5/DpsOtg7SDu4PCQ8lD0EPXg96D5YPsw/PD+wQ'
            +'CRAmEEMQYRB+EJsQuRDXEPURExExEU8RbRGMEaoRyRHoEgcSJhJFEmQShBKj'
            +'EsMS4xMDEyMTQxNjE4MTpBPFE+UUBhQnFEkUahSLFK0UzhTwFRIVNBVWFXgV'
            +'mxW9FeAWAxYmFkkWbBaPFrIW1hb6Fx0XQRdlF4kX/64X0hf3GBsYQBhlGIoY'
            +'rxjVGPoZIBlFGWsZkRm3Gd0aBBoqGlEadxqeGsUa7BsUGzsbYxuKG7Ib2hwC'
            +'HCocUhx7HKMczBz1HR4dRx1wHZkdwx3sHhYeQB5qHpQevh7pHxMfPh9pH5Qf'
            +'vx/qIBUgQSBsIJggxCDwIRwhSCF1IaEhziH7IiciVSKCIq8i3SMKIzgjZiOU'
            +'I8Ij8CQfJE0kfCSrJNolCSU4JWgllyXHJfcmJyZXJocmtyboJxgnSSd6J6sn'
            +'3CgNKD8ocSiiKNQpBik4KWspnSnQKgIqNSpoKpsqzysCKzYraSudK9EsBSw5'
            +'LG4soizXLQwtQS12Last4f8uFi5MLoIuty7uLyQvWi+RL8cv/jA1MGwwpDDb'
            +'MRIxSjGCMbox8jIqMmMymzLUMw0zRjN/M7gz8TQrNGU0njTYNRM1TTWHNcI1'
            +'/TY3NnI2rjbpNyQ3YDecN9c4FDhQOIw4yDkFOUI5fzm8Ofk6Njp0OrI67zst'
            +'O2s7qjvoPCc8ZTykPOM9Ij1hPaE94D4gPmA+oD7gPyE/YT+iP+JAI0BkQKZA'
            +'50EpQWpBrEHuQjBCckK1QvdDOkN9Q8BEA0RHRIpEzkUSRVVFmkXeRiJGZ0ar'
            +'RvBHNUd7R8BIBUhLSJFI10kdSWNJqUnwSjdKfUrESwxLU0uaS+JMKkxyTLpN'
            +'Ak3/Sk2TTdxOJU5uTrdPAE9JT5NP3VAnUHFQu1EGUVBRm1HmUjFSfFLHUxNT'
            +'X1OqU/ZUQlSPVNtVKFV1VcJWD1ZcVqlW91dEV5JX4FgvWH1Yy1kaWWlZuFoH'
            +'WlZaplr1W0VblVvlXDVchlzWXSddeF3JXhpebF69Xw9fYV+zYAVgV2CqYPxh'
            +'T2GiYfViSWKcYvBjQ2OXY+tkQGSUZOllPWWSZedmPWaSZuhnPWeTZ+loP2iW'
            +'aOxpQ2maafFqSGqfavdrT2una/9sV2yvbQhtYG25bhJua27Ebx5veG/RcCtw'
            +'hnDgcTpxlXHwcktypnMBc11zuHQUdHB0zHUodYV14XY+/3abdvh3VnezeBF4'
            +'bnjMeSp5iXnnekZ6pXsEe2N7wnwhfIF84X1BfaF+AX5ifsJ/I3+Ef+WAR4Co'
            +'gQqBa4HNgjCCkoL0g1eDuoQdhICE44VHhauGDoZyhteHO4efiASIaYjOiTOJ'
            +'mYn+imSKyoswi5aL/IxjjMqNMY2Yjf+OZo7OjzaPnpAGkG6Q1pE/kaiSEZJ6'
            +'kuOTTZO2lCCUipT0lV+VyZY0lp+XCpd1l+CYTJi4mSSZkJn8mmia1ZtCm6+c'
            +'HJyJnPedZJ3SnkCerp8dn4uf+qBpoNihR6G2oiailqMGo3aj5qRWpMelOKWp'
            +'phqmi6b9p26n4KhSqMSpN6mpqv8cqo+rAqt1q+msXKzQrUStuK4trqGvFq+L'
            +'sACwdbDqsWCx1rJLssKzOLOutCW0nLUTtYq2AbZ5tvC3aLfguFm40blKucK6'
            +'O7q1uy67p7whvJu9Fb2Pvgq+hL7/v3q/9cBwwOzBZ8Hjwl/C28NYw9TEUcTO'
            +'xUvFyMZGxsPHQce/yD3IvMk6ybnKOMq3yzbLtsw1zLXNNc21zjbOts83z7jQ'
            +'OdC60TzRvtI/0sHTRNPG1EnUy9VO1dHWVdbY11zX4Nhk2OjZbNnx2nba+9uA'
            +'3AXcit0Q3ZbeHN6i3ynfr+A24L3hROHM4lPi2+Nj4+vkc+T85YTmDeaW5x/n'
            +'qegy6LxU6Ubp0Opb6uXrcOv77IbtEe2c7ijutO9A78zwWPDl8XLx//KM8xnz'
            +'p/Q09ML1UPXe9m32+/eK+Bn4qPk4+cf6V/rn+3f8B/yY/Sn9uv5L/tz/bf//'
            +'ACwAAAAAGAAYAAAI/gCpCRxIsKDBgwipsVnIsCGbhATZTJtIkeJDiALXTFvG'
            +'seOyaWswClQjLZnJk8mmqUnDsqXLlrmYIZtJE9m0NGieSdvJk2c0Z8mOGRtK'
            +'1Jg0NGegEVvKtKlTp9DOmGnGo6pVH0CCCBkyREgQID96WK1aRtkOX7hkuYI1'
            +'i1atWrZsvaU1K9YrWbh87SCDTMctVqdAiSJVStWqw6tMlRolKhQqVrd0jCmW'
            +'oxWnR40gVbJ0CdOmTZgaiBYdqVOrHGKG4UjlCJCfQIgUMZpEidIkBixasGBA'
            +'6FEqHGGE3fBU6E8ePrATLZIkadGCFSJWLPhj6NMNMMFsZBpU5w0ePXv60QhC'
            +'hEgQAhUhVCCgM0iTjS/AahyKU4WJffsJ8icYkQJECgn6JeDFLzTc4QYUSySY'
            +'4AEkoHBCCSZwYEIJJ6BAwgFd9DLDHFQ0UcSHHxrwgQYklljiBwZwsYsMcDyR'
            +'BBEwwlhABh50sMEEEUywQQceZFDAFrrEcIUTRxhhpJEBJBmAAxdAcIEDSgag'
            +'BS8wyCGFEkhkqaWWAFjwgAUAKCGFHDBk0cYLdlgxRRRsttkmARUoUAEBU1hh'
            +'xwvUYOHCnnz2yecAGFCAwQB9ijSQAIgiSlBAADs=')

        self.remove_img = PhotoImage(format='gif',data=
             'R0lGODlhGAAYAPcAAK0AAK8AAb8AAbwAAr0AAr0AA74AAsAAAcIAAMMAAMQA'
            +'AMYAAMgAAMkAAMoAAM0BA80ABdsAAtkMDOUAA+4AAvcAAP8JCf8NDf8SDv8U'
            +'Dv8UD/8XD+McHf8YEP8ZEP8bEP8bEf8eEf8gEv8hEv8jE/8lEP8mEv8kFP8m'
            +'FP8pEv8rE/8oFf8qFf8rFf8tF/8uF/8wFv8wGP8wGf8yGP8zGv8zG/80Gf82'
            +'G/82HP83HP83Hf85HP85Hf87Hv89H/87IP89IP8/Iv8+I/8+P/9BIP9AI/9C'
            +'I/9BJP9DJP9CJf9FJf9HJf9FJv9IJ/9JJ/9MJ/9HKP9KKf9JKv9MKP9OKf9M'
            +'Kv9NKv9OK/9PLP9QLP9XMP9XMv9WM/9TNP8+RvVKTfpLTv9MT/BPU/9OUf9V'
            +'V/9WWv9WW/9YWv9YW/9YXP9bXf9nRP9qRf9sSv9uVf9xV/9yWv91Xf94X/9+'
            +'X/95YP99Y/9/ZP+EXv+AYP+DZv+GZ/+IYv+Ha/+Ja/+La/+LbP+Mbf+Pbv+O'
            +'b/+Scv+RdP+TdP+UdP+Udf+Uef+Vef+XeP+diP+eiP+fiv+fjP+ghv+jhv+m'
            +'jv+mj/+okf+qkv+rk/+tlP+xl/+zmP+1mv+0m/+3n/+4nv+5n/+5oP+6oP+6'
            +'ov/MtAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
            +'AAAAAAAAAAAAAAAAAAAAACH5BAEAAKIALAAAAAAYABgAAAj+AEUJHEiwoMGD'
            +'CBMqXMiwocOHECNKnCjQixo0GDOm2ZgRzZmPaMyYKZPGC5lQnDyp3LQpkyZM'
            +'lyxVojRJUiRHjRgtejQmTKdBhg4VIhRIEKA/ffjoyWOnDh05ceC4eTMEzKdD'
            +'ihId8oOnzRouXYgA6XHDxgwYKlKYKFHhCyhEc9hsoTIFyhIlR4r82KHjRowX'
            +'LVCQGEFBDCQtWbBckeKESRIhe/vGcMFCcIgPHiZwuGMFi5PGSCDzyFFjcmUS'
            +'lzdkwBBBwp4nVaI0MRLERw8cNGS4WHFCBIgOGjBcsAAhwAMHDho0YMB8wQIF'
            +'0BMgQHBAgIECAwgAoMi9u/fv4MMDHwwIADs=')

if __name__ == "__main__":
    app = Zambony()
    app.run()

