using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Collections.Generic;
using System.Windows.Forms;

// Windows desktop entry point. Controls only the process it starts itself.
class Launcher : Form {
    readonly string root = AppDomain.CurrentDomain.BaseDirectory;
    readonly Label status = new Label(), detail = new Label();
    readonly Button start = new Button(), stop = new Button(), open = new Button();
    readonly NotifyIcon tray = new NotifyIcon();
    readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
    Process owned;
    string stopFile, url;
    bool reachable, opening, stopping, exiting, allowClose;
    DateTime stopAt;
    static Color Green = Color.FromArgb(36,92,71);

    [STAThread] static void Main() {
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        string name="Local\\SoshyantLauncher-"+BitConverter.ToString(System.Security.Cryptography.SHA256.Create().ComputeHash(Encoding.UTF8.GetBytes(AppDomain.CurrentDomain.BaseDirectory.ToLowerInvariant()))).Replace("-", "");
        bool first;
        using (Mutex mutex=new Mutex(true,name,out first)) {
            if (!first) {MessageBox.Show("Soshyant is already in the system tray. Double-click its icon to open the launcher.","Soshyant Expert");return;}
            try {Application.Run(new Launcher());} catch(Exception error) {MessageBox.Show(error.Message,"Soshyant Expert could not open");}
        }
    }
    Launcher() {
        var settings=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(root,"config","server.json")));
        url="http://127.0.0.1:"+Convert.ToInt32(settings["port"]);
        Text="Soshyant Expert";ClientSize=new Size(590,470);MinimumSize=new Size(606,509);
        BackColor=Color.FromArgb(246,247,243);Font=new Font("Segoe UI",10);StartPosition=FormStartPosition.CenterScreen;
        var panel=new FlowLayoutPanel {Dock=DockStyle.Fill,FlowDirection=FlowDirection.TopDown,WrapContents=false,Padding=new Padding(26),AutoScroll=true};Controls.Add(panel);
        panel.Controls.Add(new Label {Text="Soshyant Expert",Font=new Font("Segoe UI",23,FontStyle.Bold),ForeColor=Green,AutoSize=true,Margin=new Padding(0,0,0,16)});
        status.AutoSize=true;status.Font=new Font("Segoe UI",13,FontStyle.Bold);panel.Controls.Add(status);
        detail.Size=new Size(530,62);detail.Margin=new Padding(0,8,0,14);panel.Controls.Add(detail);
        var row=new FlowLayoutPanel {Size=new Size(530,50)};
        Setup(start,"Start server",StartServer);Setup(open,"Open application",OpenApp);Setup(stop,"Stop server",StopServer);
        row.Controls.AddRange(new Control[]{start,open,stop});panel.Controls.Add(row);
        var links=new FlowLayoutPanel {Size=new Size(530,96),WrapContents=true};
        Add(links,"Phone / Wi-Fi access",()=>Launch(Path.Combine(root,"..","Soshyant Android","START-WIFI.bat")));
        Add(links,"Phone connection details",()=>OpenFile(Path.Combine(root,"..","Soshyant Android","dist","PHONE-CONNECTION.txt")));
        Add(links,"View server log",()=>OpenFile(Path.Combine(root,"data","desktop-server.log")));
        Add(links,"First-admin setup code",()=>OpenFile(Path.Combine(root,"data","FIRST-ADMIN-CODE.txt")));
        panel.Controls.Add(links);
        panel.Controls.Add(new Label {Text="Close this window to keep the launcher in the system tray. Use Exit in the tray menu to close it. Your documents and model settings stay on this computer.",Size=new Size(530,64),ForeColor=Color.DimGray});
        Icon=SystemIcons.Application;tray.Icon=Icon;tray.Text="Soshyant Expert";tray.Visible=true;
        var menu=new ContextMenuStrip();menu.Items.Add("Show launcher",null,(s,e)=>Reveal());menu.Items.Add("Open application",null,(s,e)=>OpenApp());menu.Items.Add("Exit",null,(s,e)=>ExitLauncher());tray.ContextMenuStrip=menu;
        tray.DoubleClick+=(s,e)=>Reveal();FormClosing+=(s,e)=>{if(!allowClose){e.Cancel=true;Hide();}};
        timer.Interval=2000;timer.Tick+=(s,e)=>RefreshHealth();timer.Start();Shown+=(s,e)=>RefreshHealth();
    }
    void Setup(Button button,string title,Action action) {button.Text=title;button.AutoSize=true;button.Height=36;button.FlatStyle=FlatStyle.Flat;button.ForeColor=Green;button.Click+=(s,e)=>Safe(action);}
    void Add(Control parent,string title,Action action) {var b=new Button();Setup(b,title,action);parent.Controls.Add(b);}
    void Safe(Action action) {try{action();}catch(Exception error){MessageBox.Show(this,error.Message,"Soshyant Expert");}}
    void Reveal() {Show();WindowState=FormWindowState.Normal;Activate();}
    void Launch(string path) {if(path==url){Process.Start(new ProcessStartInfo(path){UseShellExecute=true});return;}if(!File.Exists(path))throw new IOException("This file is unavailable: "+path);Process.Start(new ProcessStartInfo(path){UseShellExecute=true,WorkingDirectory=Path.GetDirectoryName(path)});}
    void OpenFile(string path) {if(!File.Exists(path)){MessageBox.Show(this,"This file has not been created yet. Start the server or Wi-Fi gateway first. The first-admin code is removed after initial setup.","Soshyant Expert");return;}Launch(path);}
    bool Health() {
        try {var req=(HttpWebRequest)WebRequest.Create(url+"/healthz");req.Proxy=null;req.Timeout=650;req.ReadWriteTimeout=650;
            using(var response=req.GetResponse())using(var reader=new StreamReader(response.GetResponseStream())) {
                var result=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(reader.ReadToEnd());return result.ContainsKey("status")&&Convert.ToString(result["status"])=="ok"&&result.ContainsKey("version");
            }
        } catch {return false;}
    }
    void RefreshHealth() {
        reachable=Health();
        if(owned!=null&&owned.HasExited) {int code=owned.ExitCode;owned.Dispose();owned=null;if(stopFile!=null&&File.Exists(stopFile))File.Delete(stopFile);if(!stopping&&code!=0)MessageBox.Show(this,"The server stopped. Open View server log for details.","Server needs attention");stopping=false;if(exiting){Finish();return;}}
        start.Enabled=!reachable&&owned==null&&!stopping;stop.Enabled=owned!=null&&!stopping;open.Enabled=!stopping;
        status.Text=stopping?"Stopping server safely…":reachable?"Server available":owned!=null?"Starting server…":"Server stopped";
        detail.Text=url+"\n"+(reachable?(owned!=null?"Started by this launcher.":"Started outside this launcher. Stop it from its original window."):"Start the server, then open the application.");
        if(stopping&&(DateTime.UtcNow-stopAt).TotalSeconds>30){detail.Text="Shutdown is taking longer than usual. Waiting for current work to stop. No process will be forcibly terminated.";}
        if(opening&&reachable){opening=false;Launch(url);}
    }
    void StartServer() {
        if(owned!=null||Health())return;
        Directory.CreateDirectory(Path.Combine(root,"data"));stopFile=Path.Combine(root,"data","launcher-stop-"+Guid.NewGuid().ToString("N"));
        string python=Path.Combine(root,"runtime","python.exe");if(!File.Exists(python))throw new IOException("The bundled Python runtime is missing.");
        owned=Process.Start(new ProcessStartInfo(python,"\""+Path.Combine(root,"tools","desktop_host.py")+"\" --desktop-stop-file \""+stopFile+"\"") {UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=root});RefreshHealth();
    }
    void OpenApp() {Safe(()=>{if(Health())Launch(url);else {opening=true;StartServer();}});}
    void StopServer() {if(owned==null||owned.HasExited||stopping)return;File.WriteAllText(stopFile,"");stopAt=DateTime.UtcNow;stopping=true;opening=false;RefreshHealth();}
    void ExitLauncher() {
        Safe(()=>{if(owned!=null&&!owned.HasExited){if(MessageBox.Show(this,"Stop the server started by this launcher and exit?", "Exit Soshyant",MessageBoxButtons.YesNo,MessageBoxIcon.Question)!=DialogResult.Yes)return;exiting=true;Reveal();StopServer();}else Finish();});
    }
    void Finish() {allowClose=true;timer.Stop();tray.Visible=false;tray.Dispose();Close();}
}
