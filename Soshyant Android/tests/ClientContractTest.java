import com.soshyant.expert.ApiClient;
import java.nio.file.*;
import org.json.*;

/** Exercises the exact Java transport included in the APK against real HTTPS. */
public class ClientContractTest {
    private static void check(boolean ok,String message){if(!ok)throw new AssertionError(message);}
    public static void main(String[] args) throws Exception {
        String address=args[0];byte[] ca=Files.readAllBytes(Paths.get(args[1]));
        for(String bad:new String[]{"http://127.0.0.1:8095","https://user:pass@example.com","https://example.com/path","https://example.com?token=bad"}){
            try{ApiClient.validateServer(bad);throw new AssertionError("Unsafe server URL accepted");}catch(java.io.IOException expected){}
        }
        check(ApiClient.validateServer("https://example.com:443/").getPort()==-1,"Default HTTPS port not normalized");
        ApiClient client=new ApiClient(address,ca);
        check(client.object("/healthz").getString("status").equals("ok"),"HTTPS gateway health");
        try{client.object("/api/conversations");throw new AssertionError("Anonymous data access");}catch(ApiClient.ApiException expected){check(expected.status==403,"Anonymous status");}
        client.login("phone-user","phone-test-password");
        check(client.object("/api/me").getString("username").equals("phone-user"),"Secure session cookie");
        JSONObject status=client.object("/api/status");
        String conversation=client.post("/api/conversations",new JSONObject()).getString("id");
        String job=client.post("/api/ask",new JSONObject().put("conversation_id",conversation).put("question","What is the warranty?")
            .put("response_language","en").put("model_selection",status.getJSONObject("model").getString("selection_id"))).getString("job_id");
        JSONObject outcome=null;
        for(int i=0;i<100;i++){outcome=client.object("/api/jobs/"+job);if(outcome.getString("status").equals("done"))break;Thread.sleep(100);}
        check(outcome.getString("status").equals("done"),"Generation job completion");
        check(outcome.getJSONObject("result").getJSONArray("citations").length()==1,"Source citations");
        check(client.array("/api/conversations/"+conversation+"/messages").length()==2,"Conversation history");
        int messageId=client.array("/api/conversations/"+conversation+"/messages").getJSONObject(1).getInt("id");
        client.post("/api/feedback",new JSONObject().put("message_id",messageId).put("rating","helpful").put("note","Phone feedback"));
        client.post("/api/conversations/"+conversation+"/rename",new JSONObject().put("title","Warranty research"));
        check(client.array("/api/conversations").getJSONObject(0).getString("title").equals("Warranty research"),"Rename persisted");
        try{client.post("/api/conversations/"+conversation+"/delete",new JSONObject());throw new AssertionError("Unconfirmed deletion accepted");}catch(ApiClient.ApiException expected){check(expected.status==400,"Confirmation required");}
        client.post("/api/conversations/"+conversation+"/delete",new JSONObject().put("confirm",true));
        check(client.array("/api/conversations").length()==0,"Chat deletion persisted");
        try{client.object("/api/jobs/"+job);throw new AssertionError("Deleted answer retained in job API");}catch(ApiClient.ApiException expected){check(expected.status==403,"Deleted answer job removed");}
        try{client.object("/api/users");throw new AssertionError("Administrative route exposed");}catch(ApiClient.ApiException expected){check(expected.status==404,"Gateway route scope");}
        client.post("/api/logout",new JSONObject());
        try{client.object("/api/me");throw new AssertionError("Logout failed");}catch(ApiClient.ApiException expected){check(expected.status==403,"Revoked session");}
        boolean rejected=false;
        try{new ApiClient(address,null).object("/healthz");}catch(javax.net.ssl.SSLException expected){rejected=true;}
        check(rejected,"An untrusted certificate was accepted");
        String wrong=address.replace("127.0.0.1","localhost");rejected=false;
        try{new ApiClient(wrong,ca).object("/healthz");}catch(javax.net.ssl.SSLException expected){rejected=true;}
        check(rejected,"Hostname mismatch was accepted");
        System.out.println("PASS: HTTPS trust, hostname checks, login cookies, CSRF, ask/poll, citations, history, rename, confirmed deletion, feedback, logout, and gateway route scope.");
    }
}
