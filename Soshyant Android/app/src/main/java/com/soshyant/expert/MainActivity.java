package com.soshyant.expert;

import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.text.InputFilter;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.util.concurrent.*;
import javax.net.ssl.SSLException;
import org.json.*;

public class MainActivity extends Activity {
    private static final int GREEN=0xff245c47, INK=0xff213d35, MUTED=0xff6d7f73, PAPER=0xfff6f7f3;
    private final ExecutorService worker=Executors.newFixedThreadPool(2);
    private ApiClient api;
    private boolean signedIn=false,busy=false,persian=false;
    private int epoch=0;
    private String conversation="",pendingJob="",draft="",pendingQuestion="",notice="",phase="",account="";
    private String chatTitle="",exportText="";
    private JSONObject status;
    private JSONArray messages=new JSONArray();
    private LinearLayout root,content;
    private EditText address,username,password,question;
    private TextView phaseView;
    private Button send,cancel,history,fresh,logout;
    private byte[] certificate;
    private android.content.SharedPreferences preferences;
    private interface Task { void run() throws Exception; }

    private String t(String en,String fa) { return persian?fa:en; }
    private int dp(int value) { return (int)(getResources().getDisplayMetrics().density*value+.5f); }
    private GradientDrawable box(int color) { GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(14));return d; }
    private TextView text(String value,int size,int color) {
        TextView v=new TextView(this);v.setText(value);v.setTextSize(size);v.setTextColor(color);v.setPadding(0,dp(5),0,dp(8));
        v.setTextDirection(View.TEXT_DIRECTION_FIRST_STRONG);return v;
    }
    private Button button(String label,Runnable action) {
        Button b=new Button(this);b.setText(label);b.setAllCaps(false);b.setTextColor(GREEN);
        b.setOnClickListener(v->action.run());return b;
    }
    private EditText input(String hint,int type) {
        EditText field=new EditText(this);field.setSingleLine(true);field.setHint(hint);field.setTextSize(15);field.setInputType(type);
        field.setTextColor(INK);field.setPadding(dp(12),dp(9),dp(12),dp(9));field.setBackground(box(Color.WHITE));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,dp(52));p.setMargins(0,dp(6),0,dp(12));field.setLayoutParams(p);return field;
    }
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        preferences=getSharedPreferences("connection",MODE_PRIVATE);persian=preferences.getBoolean("persian",false);
        File ca=new File(getFilesDir(),"server-ca.crt");
        try { if(ca.exists()) certificate=read(new FileInputStream(ca),128*1024); } catch(Exception e) { notice=t("Import the server CA certificate again.","گواهی CA سرور را دوباره وارد کنید."); }
        render();
    }
    private void render() {
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(PAPER);
        root.setLayoutDirection(persian?View.LAYOUT_DIRECTION_RTL:View.LAYOUT_DIRECTION_LTR);
        root.setOnApplyWindowInsetsListener((v,insets)->{
            if(Build.VERSION.SDK_INT>=30){
                android.graphics.Insets edges=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout()|WindowInsets.Type.ime());
                v.setPadding(edges.left,edges.top,edges.right,edges.bottom);
            }else v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());
            return insets;
        });
        setContentView(root);
        LinearLayout head=new LinearLayout(this);head.setPadding(dp(18),dp(14),dp(12),dp(14));head.setGravity(Gravity.CENTER_VERTICAL);head.setBackgroundColor(GREEN);
        TextView brand=text("Soshyant Expert",21,Color.WHITE);brand.setTypeface(null,Typeface.BOLD);head.addView(brand,new LinearLayout.LayoutParams(0,-2,1));
        Spinner language=new Spinner(this);ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"English","فارسی"});
        language.setAdapter(adapter);language.setBackground(box(0xffe9f0e8));language.setSelection(persian?1:0);head.addView(language,new LinearLayout.LayoutParams(dp(112),dp(42)));
        language.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(android.widget.AdapterView<?> p){}
            public void onItemSelected(android.widget.AdapterView<?> p,View v,int position,long id){
                if(persian==(position==1))return;
                if(signedIn && question!=null)draft=question.getText().toString();
                String a=address==null?preferences.getString("server",""):address.getText().toString();
                persian=position==1;preferences.edit().putBoolean("persian",persian).putString("server",a).apply();render();
            }
        });root.addView(head);
        if(signedIn) renderChat();else renderLogin();
    }
    private void renderLogin() {
        ScrollView scroll=new ScrollView(this);content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(24),dp(22),dp(24),dp(28));scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        TextView title=text(t("Your knowledge, on your Wi-Fi","دانش شما در شبکه داخلی شما"),25,INK);title.setTypeface(null,Typeface.BOLD);content.addView(title);
        content.addView(text(t("Connect to your Soshyant server. Your account and documents are managed on the computer.","به سرور سوشیانت وصل شوید. حساب و اسناد از کامپیوتر مدیریت می‌شوند."),14,MUTED));
        content.addView(text(t("Server address","نشانی سرور"),13,INK));
        address=input("https://192.168.1.10:8095",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);address.setTextDirection(View.TEXT_DIRECTION_LTR);address.setText(preferences.getString("server",""));content.addView(address);
        content.addView(button(t("Test connection","بررسی اتصال"),()->{
            String target=address.getText().toString();byte[] ca=certificate;
            work(()->{ApiClient probe=new ApiClient(target,ca);probe.object("/healthz");preferences.edit().putString("server",probe.address()).apply();notice=t("Secure connection verified. You can sign in.","اتصال امن تأیید شد؛ وارد حساب شوید.");});
        }));
        content.addView(button(t("Import server CA certificate","واردکردن گواهی CA سرور"),()->{
            if(busy)return;
            preferences.edit().putString("server",address.getText().toString()).apply();
            Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT);intent.setType("*/*");intent.addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(intent,7);
        }));
        content.addView(button(t("Use Android's trusted certificates","استفاده از گواهی‌های مورد اعتماد اندروید"),()->{
            if(busy)return;certificate=null;new File(getFilesDir(),"server-ca.crt").delete();notice=t("Using Android's certificate trust store.","گواهی‌های مورد اعتماد اندروید استفاده می‌شوند.");render();
        }));
        content.addView(text(certificate==null?t("No private CA imported.","گواهی خصوصی وارد نشده است."):t("Your server CA is imported. Hostname verification stays enabled.","گواهی CA وارد شده است؛ اعتبارسنجی نام سرور فعال می‌ماند."),12,MUTED));
        if(certificate!=null)try{
            java.security.cert.Certificate ca=java.security.cert.CertificateFactory.getInstance("X.509").generateCertificate(new ByteArrayInputStream(certificate));
            byte[] hash=java.security.MessageDigest.getInstance("SHA-256").digest(ca.getEncoded());StringBuilder hex=new StringBuilder();
            for(byte value:hash){hex.append(Character.forDigit((value>>4)&15,16));hex.append(Character.forDigit(value&15,16));}
            TextView fingerprint=text("CA SHA-256: "+hex,11,MUTED);fingerprint.setTextIsSelectable(true);fingerprint.setTextDirection(View.TEXT_DIRECTION_LTR);content.addView(fingerprint);
        }catch(Exception ignored){}
        content.addView(text(t("Username","نام کاربری"),13,INK));username=input(t("Your account","حساب شما"),InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD);content.addView(username);
        content.addView(text(t("Password","گذرواژه"),13,INK));password=input("",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);content.addView(password);
        Button sign=button(t("Sign in","ورود"),()->{
            if(busy)return;
            final String host=address.getText().toString(),user=username.getText().toString(),secret=password.getText().toString();final byte[] ca=certificate;
            if(user.isEmpty()||secret.isEmpty()){notice=t("Enter your username and password.","نام کاربری و گذرواژه را وارد کنید.");render();return;}
            work(()->{
                ApiClient next=new ApiClient(host,ca);
                if(next.object("/api/bootstrap").optBoolean("setup_required"))throw new IOException(t("Create the first administrator on the computer before signing in here.","ابتدا حساب مدیر اولیه را روی کامپیوتر بسازید."));
                next.login(user,secret);account=next.object("/api/me").getString("username");api=next;signedIn=true;
                preferences.edit().putString("server",next.address()).apply();status=api.object("/api/status");
                JSONArray chats=api.array("/api/conversations");conversation=chats.length()>0?chats.getJSONObject(0).getString("id"):"";loadMessages();notice="";
            });
        });sign.setBackground(box(GREEN));sign.setTextColor(Color.WHITE);content.addView(sign);
        phaseView=text(busy?t("Connecting…","در حال اتصال…"):notice,14,INK);content.addView(phaseView);
        content.addView(text(t("Use HTTPS and the server's Wi-Fi address, not localhost. Passwords and sessions are kept in memory only. No microphone or cloud API key is needed on this phone.","از HTTPS و نشانی وای‌فای سرور استفاده کنید، نه localhost. گذرواژه و نشست فقط در حافظه می‌مانند. گوشی به میکروفون یا کلید API ابری نیاز ندارد."),12,MUTED));
    }
    private void renderChat() {
        LinearLayout tools=new LinearLayout(this);tools.setPadding(dp(10),dp(3),dp(10),dp(3));
        history=button(t("History","گفت‌وگوها"),this::chooseHistory);fresh=button(t("New chat","گفت‌وگوی تازه"),()->work(()->{conversation=api.post("/api/conversations",new JSONObject()).getString("id");messages=new JSONArray();chatTitle="";draft="";}));
        logout=button(t("Sign out","خروج"),()->{
            if(busy)return;work(()->{try{api.post("/api/logout",new JSONObject());}finally{api.clear();signedIn=false;conversation="";messages=new JSONArray();pendingJob="";draft="";notice="";}});
        });for(Button b:new Button[]{history,fresh,logout})tools.addView(b,new LinearLayout.LayoutParams(0,-2,1));root.addView(tools);
        LinearLayout info=new LinearLayout(this);info.setOrientation(LinearLayout.VERTICAL);info.setPadding(dp(18),0,dp(18),dp(3));
        info.addView(text(account+" · "+preferences.getString("server",""),11,MUTED));
        JSONObject model=status==null?new JSONObject():status.optJSONObject("model");
        if(model!=null){
            boolean cloud=model.optString("kind").equals("cloud");
            TextView provider=text((cloud?t("API model: ","مدل API: "):t("Local model: ","مدل محلی: "))+model.optString("name"),12,INK);info.addView(provider);
            if(cloud){TextView warning=text(t("Answer context is sent by your server to: ","اطلاعات پاسخ از سرور شما به این مقصد ارسال می‌شود: ")+model.optString("base_url"),12,0xff835c26);warning.setBackground(box(0xfffff3df));info.addView(warning);}
        }root.addView(info);
        LinearLayout heading=new LinearLayout(this);heading.setPadding(dp(18),0,dp(12),0);heading.setGravity(Gravity.CENTER_VERTICAL);
        TextView title=text(chatTitle.isEmpty()?t("New conversation","گفت‌وگوی تازه"):chatTitle,18,INK);title.setTypeface(null,Typeface.BOLD);title.setMaxLines(2);
        heading.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        Button options=button("⋮",()->manageChat(conversation,chatTitle));options.setContentDescription(t("Chat options","گزینه‌های گفت‌وگو"));options.setEnabled(!busy&&pendingJob.isEmpty()&&!conversation.isEmpty());heading.addView(options);root.addView(heading);
        ScrollView scroll=new ScrollView(this);LinearLayout feed=new LinearLayout(this);feed.setOrientation(LinearLayout.VERTICAL);feed.setPadding(dp(16),dp(12),dp(16),dp(18));scroll.addView(feed);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        if(messages.length()==0 && pendingJob.isEmpty())feed.addView(text(t("Ask a question about your documents. Answers include source passages you can open.","درباره اسناد سؤال بپرسید. همراه پاسخ، شاهدهای قابل بررسی نمایش داده می‌شوند."),17,MUTED));
        for(int i=0;i<messages.length();i++){JSONObject message=messages.optJSONObject(i);if(message!=null)addMessage(feed,message);}
        if(!pendingJob.isEmpty())try{addMessage(feed,new JSONObject().put("role","user").put("content",pendingQuestion));}catch(JSONException ignored){}
        LinearLayout composer=new LinearLayout(this);composer.setOrientation(LinearLayout.VERTICAL);composer.setPadding(dp(16),dp(3),dp(16),dp(10));
        phaseView=text(phase.isEmpty()?notice:phase,12,MUTED);composer.addView(phaseView);
        question=input(t("Ask your question…","پرسش خود را بنویسید…"),InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        question.setSingleLine(false);question.setMinLines(2);question.setMaxLines(5);question.setFilters(new InputFilter[]{new InputFilter.LengthFilter(4000)});question.setText(draft);question.setTextDirection(View.TEXT_DIRECTION_FIRST_STRONG);composer.addView(question);
        LinearLayout actions=new LinearLayout(this);send=button(pendingJob.isEmpty()?t("Send question","ارسال پرسش"):t("Resume response","ادامه دریافت پاسخ"),this::sendQuestion);send.setBackground(box(GREEN));send.setTextColor(Color.WHITE);
        cancel=button(t("Stop","توقف"),this::cancelQuestion);Button refresh=button(t("Refresh","تازه‌سازی"),()->work(()->{status=api.object("/api/status");loadMessages();}));
        actions.addView(send,new LinearLayout.LayoutParams(0,dp(48),1));actions.addView(cancel);actions.addView(refresh);composer.addView(actions);root.addView(composer);controls();
        scroll.post(()->scroll.fullScroll(View.FOCUS_DOWN));
    }
    private void addMessage(LinearLayout feed,JSONObject message) {
        boolean user=message.optString("role").equals("user");LinearLayout card=new LinearLayout(this);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(dp(15),dp(10),dp(15),dp(12));card.setBackground(box(user?0xffe9f0e8:Color.WHITE));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.setMargins(user?dp(24):0,0,user?0:dp(14),dp(14));feed.addView(card,p);
        card.addView(text(user?t("YOU","شما"):"Soshyant Expert",11,MUTED));TextView body=text(message.optString("content"),16,INK);body.setTextIsSelectable(true);if(!user)body.setText(AnswerText.format(message.optString("content")));card.addView(body);
        if(message.optDouble("created",0)>0)card.addView(text(android.text.format.DateFormat.getMediumDateFormat(this).format(new java.util.Date((long)(message.optDouble("created")*1000)))+" · "+android.text.format.DateFormat.getTimeFormat(this).format(new java.util.Date((long)(message.optDouble("created")*1000))),11,MUTED));
        if(!user){
            LinearLayout actions=new LinearLayout(this);
            actions.addView(button(t("Copy","کپی"),()->{((android.content.ClipboardManager)getSystemService(CLIPBOARD_SERVICE)).setPrimaryClip(ClipData.newPlainText("Answer",answerWithSources(message)));Toast.makeText(this,t("Answer copied","پاسخ کپی شد"),Toast.LENGTH_SHORT).show();}),new LinearLayout.LayoutParams(0,-2,1));
            actions.addView(button(t("Share","اشتراک"),()->shareText(answerWithSources(message))),new LinearLayout.LayoutParams(0,-2,1));
            if(message.optInt("id")>0)actions.addView(button(t("Feedback","بازخورد"),()->feedback(message.optInt("id"))),new LinearLayout.LayoutParams(0,-2,1));card.addView(actions);
        }
        JSONObject result=message.optJSONObject("result");JSONArray sources=result==null?null:result.optJSONArray("citations");
        if(sources!=null)for(int i=0;i<sources.length();i++){
            JSONObject source=sources.optJSONObject(i);if(source==null)continue;
            TextView passage=text(source.optString("text"),14,INK);passage.setTextIsSelectable(true);passage.setVisibility(View.GONE);
            Button open=button("["+source.optInt("n")+"] "+source.optString("title")+" · "+source.optString("location")+" · v"+source.optInt("document_version"),()->passage.setVisibility(passage.getVisibility()==View.GONE?View.VISIBLE:View.GONE));
            open.setGravity(Gravity.START);open.setTextSize(12);card.addView(open);card.addView(passage);
        }
    }
    private void loadMessages() throws Exception {
        messages=conversation.isEmpty()?new JSONArray():api.array("/api/conversations/"+conversation+"/messages");chatTitle="";
        JSONArray chats=api.array("/api/conversations");for(int i=0;i<chats.length();i++){JSONObject chat=chats.getJSONObject(i);if(chat.optString("id").equals(conversation))chatTitle=chat.optString("title");}
    }
    private String answerWithSources(JSONObject message) {
        StringBuilder value=new StringBuilder(message.optString("content"));JSONObject result=message.optJSONObject("result");JSONArray sources=result==null?null:result.optJSONArray("citations");
        if(sources!=null&&sources.length()>0){value.append("\n\n").append(t("Sources","منابع"));for(int i=0;i<sources.length();i++){JSONObject source=sources.optJSONObject(i);if(source!=null)value.append("\n[").append(source.optInt("n")).append("] ").append(source.optString("title")).append(" · ").append(source.optString("location")).append(" · v").append(source.optInt("document_version"));}}
        return value.toString();
    }
    private void shareText(String value) {
        if(value.length()>100000){new AlertDialog.Builder(this).setTitle(t("Save this conversation","ذخیره گفت‌وگو")).setMessage(t("This text is too long to share directly. Save it as a text file instead.","این متن برای اشتراک مستقیم طولانی است. آن را در فایل متنی ذخیره کنید.")).setPositiveButton(t("Save file","ذخیره فایل"),(d,w)->exportText(value)).setNegativeButton(t("Cancel","انصراف"),null).show();return;}
        Intent share=new Intent(Intent.ACTION_SEND);share.setType("text/plain");share.putExtra(Intent.EXTRA_TEXT,value);startActivity(Intent.createChooser(share,t("Share text","اشتراک متن")));
    }
    private void exportText(String value) {
        exportText=value;Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType("text/plain");intent.putExtra(Intent.EXTRA_TITLE,"Soshyant-conversation.txt");startActivityForResult(intent,8);
    }
    private void feedback(int id) {
        if(busy)return;
        new AlertDialog.Builder(this).setTitle(t("Was this answer useful?","آیا پاسخ مفید بود؟"))
            .setItems(new String[]{t("Helpful","مفید بود"),t("Incorrect or incomplete","نادرست یا ناقص")},(d,which)->{
                EditText note=input(t("Optional note","توضیح اختیاری"),InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);note.setSingleLine(false);note.setFilters(new InputFilter[]{new InputFilter.LengthFilter(1000)});
                new AlertDialog.Builder(this).setTitle(t("Send feedback","ارسال بازخورد")).setView(note).setPositiveButton(t("Send","ارسال"),(dialog,w)->work(()->{api.post("/api/feedback",new JSONObject().put("message_id",id).put("rating",which==0?"helpful":"incorrect").put("note",note.getText().toString()));notice=t("Feedback saved.","بازخورد ذخیره شد.");})).setNegativeButton(t("Cancel","انصراف"),null).show();
            }).setNegativeButton(t("Cancel","انصراف"),null).show();
    }
    private void manageChat(String id,String title) {
        if(busy||!pendingJob.isEmpty()||id.isEmpty())return;
        new AlertDialog.Builder(this).setTitle(title.isEmpty()?t("Chat options","گزینه‌های گفت‌وگو"):title)
            .setItems(new String[]{t("Rename chat","تغییر نام"),t("Share conversation","اشتراک گفت‌وگو"),t("Save as text file","ذخیره فایل متنی"),t("Delete chat","حذف گفت‌وگو")},(d,which)->{
                if(which==0){EditText name=input(t("Chat title","عنوان گفت‌وگو"),InputType.TYPE_CLASS_TEXT);name.setFilters(new InputFilter[]{new InputFilter.LengthFilter(100)});name.setText(title);
                    AlertDialog rename=new AlertDialog.Builder(this).setTitle(t("Rename chat","تغییر نام")).setView(name).setPositiveButton(t("Save","ذخیره"),null).setNegativeButton(t("Cancel","انصراف"),null).create();rename.setOnShowListener(v->rename.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(w->{String value=name.getText().toString().trim();if(value.isEmpty()){name.setError(t("Enter a title","عنوان وارد کنید"));return;}rename.dismiss();work(()->{api.post("/api/conversations/"+id+"/rename",new JSONObject().put("title",value));if(id.equals(conversation))chatTitle=value;});}));rename.show();
                }else if(which==1||which==2){work(()->{JSONArray rows=api.array("/api/conversations/"+id+"/messages");StringBuilder value=new StringBuilder(title);for(int i=0;i<rows.length();i++){JSONObject row=rows.getJSONObject(i);value.append("\n\n").append(row.optString("role").equals("user")?t("You: ","شما: "):"Soshyant Expert: ").append(answerWithSources(row));}String exported=value.toString();runOnUiThread(()->{if(!isDestroyed()){if(which==2)exportText(exported);else shareText(exported);}});});
                }else new AlertDialog.Builder(this).setTitle(t("Delete this chat?","این گفت‌وگو حذف شود؟"))
                    .setMessage(t("This permanently removes the conversation, answers and feedback from your account on the server. Existing backups and previously shared copies remain.","گفت‌وگو، پاسخ‌ها و بازخوردهایش از حساب شما روی سرور حذف می‌شوند. نسخه‌های پشتیبان و متن‌های قبلاً به‌اشتراک‌گذاشته‌شده باقی می‌مانند."))
                    .setNegativeButton(t("Cancel","انصراف"),null).setPositiveButton(t("Delete permanently","حذف دائمی"),(dialog,w)->work(()->{api.post("/api/conversations/"+id+"/delete",new JSONObject().put("confirm",true));if(id.equals(conversation)){conversation="";chatTitle="";messages=new JSONArray();draft="";}notice=t("Chat deleted.","گفت‌وگو حذف شد.");})).show();
            }).setNegativeButton(t("Close","بستن"),null).show();
    }
    private void chooseHistory() {
        if(busy||!pendingJob.isEmpty())return;
        work(()->{
            JSONArray chats=api.array("/api/conversations");
            runOnUiThread(()->{
                if(isDestroyed())return;
                LinearLayout panel=new LinearLayout(this);panel.setOrientation(LinearLayout.VERTICAL);panel.setPadding(dp(16),0,dp(16),0);panel.setLayoutDirection(persian?View.LAYOUT_DIRECTION_RTL:View.LAYOUT_DIRECTION_LTR);
                EditText search=input(t("Search conversations…","جست‌وجوی گفت‌وگوها…"),InputType.TYPE_CLASS_TEXT);panel.addView(search);
                ScrollView scroll=new ScrollView(this);LinearLayout list=new LinearLayout(this);list.setOrientation(LinearLayout.VERTICAL);scroll.addView(list);panel.addView(scroll,new LinearLayout.LayoutParams(-1,Math.min(dp(360),getResources().getDisplayMetrics().heightPixels/2)));
                AlertDialog dialog=new AlertDialog.Builder(this).setTitle(t("Your conversations","گفت‌وگوهای شما")).setView(panel).setNegativeButton(t("Close","بستن"),null).create();
                Runnable filter=()->{list.removeAllViews();String query=search.getText().toString().trim().toLowerCase(java.util.Locale.ROOT);int count=0;
                    for(int i=0;i<chats.length();i++){JSONObject chat=chats.optJSONObject(i);String title=chat.optString("title"),id=chat.optString("id");if(!title.toLowerCase(java.util.Locale.ROOT).contains(query))continue;count++;
                        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);Button open=button((id.equals(conversation)?"● ":"")+title+"\n"+android.text.format.DateFormat.getMediumDateFormat(this).format(new java.util.Date((long)(chat.optDouble("updated")*1000))),()->{dialog.dismiss();conversation=id;draft="";work(this::loadMessages);});open.setGravity(Gravity.START);open.setTextSize(14);row.addView(open,new LinearLayout.LayoutParams(0,-2,1));Button more=button("⋮",()->{dialog.dismiss();manageChat(id,title);});more.setContentDescription(t("Chat options for ","گزینه‌های گفت‌وگو ")+title);row.addView(more);list.addView(row);
                    }if(count==0)list.addView(text(t("No conversations found.","گفت‌وگویی پیدا نشد."),15,MUTED));};
                search.addTextChangedListener(new android.text.TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){filter.run();}public void afterTextChanged(android.text.Editable e){}});filter.run();dialog.show();dialog.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN);
            });
        });
    }
    private void sendQuestion() {
        if(busy)return;
        if(!pendingJob.isEmpty()){work(this::poll);return;}
        draft=question.getText().toString();if(draft.trim().isEmpty())return;
        pendingQuestion=draft;final String language=persian?"fa":"en";
        work(()->{
            if(conversation.isEmpty())conversation=api.post("/api/conversations",new JSONObject()).getString("id");
            JSONObject payload=new JSONObject().put("conversation_id",conversation).put("question",pendingQuestion).put("response_language",language);
            if(status!=null)payload.put("model_selection",status.getJSONObject("model").optString("selection_id"));
            try{
                pendingJob=api.post("/api/ask",payload).getString("job_id");draft="";
                runOnUiThread(()->{if(!isDestroyed())render();});poll();
            }catch(Exception error){try{status=api.object("/api/status");loadMessages();}catch(Exception ignored){}throw error;}
        });
    }
    private void poll() throws Exception {
        long deadline=System.currentTimeMillis()+10*60*1000;
        while(!pendingJob.isEmpty() && !Thread.currentThread().isInterrupted()) {
            JSONObject job=api.object("/api/jobs/"+pendingJob);String state=job.getString("status");
            phase=job.optString("phase");runOnUiThread(()->{if(phaseView!=null && !isDestroyed())phaseView.setText(phase);});
            if(state.equals("done")){pendingJob="";pendingQuestion="";phase="";notice="";loadMessages();status=api.object("/api/status");return;}
            if(state.equals("failed") || state.equals("canceled")){
                pendingJob="";draft=pendingQuestion;pendingQuestion="";phase="";
                throw new IOException(state.equals("failed")?job.optString("error"):t("The request was stopped.","درخواست متوقف شد."));
            }
            if(System.currentTimeMillis()>deadline)throw new IOException(t("The server is still working. Tap Resume response to keep checking.","سرور هنوز مشغول است. برای پیگیری، ادامه دریافت پاسخ را بزنید."));
            Thread.sleep(1000);
        }
    }
    private void cancelQuestion() {
        if(pendingJob.isEmpty() || api==null)return;
        final String job=pendingJob;final ApiClient connection=api;
        cancel.setEnabled(false);worker.execute(()->{
            try { connection.post("/api/jobs/"+job+"/cancel",new JSONObject()); }
            catch(Exception e){runOnUiThread(()->{if(!isDestroyed()){Toast.makeText(this,friendly(e),Toast.LENGTH_LONG).show();if(cancel!=null)cancel.setEnabled(!pendingJob.isEmpty());}});}
        });
    }
    private void controls() {
        if(!signedIn || send==null)return;send.setEnabled(!busy);history.setEnabled(!busy && pendingJob.isEmpty());fresh.setEnabled(!busy && pendingJob.isEmpty());logout.setEnabled(!busy);question.setEnabled(!busy && pendingJob.isEmpty());cancel.setVisibility(pendingJob.isEmpty()?View.GONE:View.VISIBLE);cancel.setEnabled(!pendingJob.isEmpty());
    }
    private String friendly(Exception error) {
        if(error instanceof SSLException)return t("TLS verification failed. Check the server address and import its CA certificate.","اعتبارسنجی TLS ناموفق بود. نشانی سرور و گواهی CA آن را بررسی کنید.");
        if(error instanceof java.net.ConnectException || error instanceof java.net.SocketTimeoutException || error instanceof java.net.UnknownHostException)return t("Cannot reach the server. Check the Wi-Fi, LAN server, firewall, and address.","اتصال به سرور برقرار نشد. وای‌فای، اجرای سرور، فایروال و نشانی را بررسی کنید.");
        return error.getMessage()==null?t("The request could not be completed.","درخواست کامل نشد."):error.getMessage();
    }
    private void work(Task task) {
        if(busy)return;if(signedIn && question!=null && pendingJob.isEmpty())draft=question.getText().toString();busy=true;notice="";controls();if(phaseView!=null)phaseView.setText(t("Working…","در حال انجام…"));final int generation=epoch;
        worker.execute(()->{
            String error=null;
            try{task.run();}catch(Exception e){error=friendly(e);if(e instanceof ApiClient.ApiException && ((ApiClient.ApiException)e).status==403){if(api!=null)api.clear();signedIn=false;pendingJob="";}}
            final String message=error;
            runOnUiThread(()->{if(isDestroyed()||generation!=epoch)return;busy=false;if(message!=null){notice=message;phase="";}render();});
        });
    }
    private static byte[] read(InputStream source,int maximum) throws Exception {
        try(InputStream in=source;ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] block=new byte[4096];int n;while((n=in.read(block))!=-1){if(out.size()+n>maximum)throw new IOException("Certificate file too large.");out.write(block,0,n);}return out.toByteArray();
        }
    }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if(request==8){
            String value=exportText;exportText="";if(result!=RESULT_OK||data==null)return;
            android.net.Uri destination=data.getData();work(()->{try(OutputStream out=getContentResolver().openOutputStream(destination,"wt")){if(out==null)throw new IOException("Could not open the selected file.");out.write(value.getBytes(java.nio.charset.StandardCharsets.UTF_8));}notice=t("Conversation saved.","گفت‌وگو ذخیره شد.");});return;
        }
        if(request!=7||result!=RESULT_OK||data==null)return;
        try {byte[] ca=read(getContentResolver().openInputStream(data.getData()),128*1024);ApiClient.certificateTrust(ca);
            try(FileOutputStream out=openFileOutput("server-ca.crt",MODE_PRIVATE)){out.write(ca);}certificate=ca;notice=t("Server CA imported. Test the connection next.","گواهی CA وارد شد؛ اتصال را بررسی کنید.");
        }catch(Exception e){notice=t("Could not import this CA certificate. Use the public server-ca.crt file.","گواهی CA وارد نشد. فایل عمومی server-ca.crt را انتخاب کنید.");}render();
    }
    @Override protected void onDestroy(){epoch++;worker.shutdownNow();if(api!=null)api.clear();super.onDestroy();}
}
