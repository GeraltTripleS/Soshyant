package com.soshyant.expert;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.*;
import javax.net.ssl.*;
import org.json.*;

/** One server, in-memory cookies only, no redirects or certificate bypass. */
public final class ApiClient {
    public static final class ApiException extends IOException {
        public final int status;
        ApiException(int status, String message) { super(message); this.status=status; }
    }
    private final URI origin;
    private final SSLSocketFactory tls;
    private final CookieManager cookies=new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
    private String csrf="";

    public static URI validateServer(String value) throws IOException {
        try {
            URI uri=new URI(value.trim());
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost()==null || uri.getUserInfo()!=null
                || uri.getQuery()!=null || uri.getFragment()!=null || (uri.getPort()!=-1 && (uri.getPort()<1 || uri.getPort()>65535))
                || (uri.getPath()!=null && !uri.getPath().isEmpty() && !uri.getPath().equals("/")))
                throw new IOException("Enter the server's HTTPS address without a path, password, or query.");
            return new URI("https",null,uri.getHost(),uri.getPort()==443?-1:uri.getPort(),"/",null,null);
        } catch (URISyntaxException e) { throw new IOException("The server address is invalid."); }
    }

    public static SSLSocketFactory certificateTrust(byte[] certificate) throws Exception {
        X509Certificate ca=(X509Certificate)CertificateFactory.getInstance("X.509").generateCertificate(new ByteArrayInputStream(certificate));
        ca.checkValidity();
        if (ca.getBasicConstraints()<0) throw new IOException("Choose the server CA certificate, not its server certificate or private key.");
        KeyStore store=KeyStore.getInstance(KeyStore.getDefaultType()); store.load(null,null); store.setCertificateEntry("server-ca",ca);
        TrustManagerFactory factory=TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());factory.init(store);
        SSLContext context=SSLContext.getInstance("TLS");context.init(null,factory.getTrustManagers(),null);
        return context.getSocketFactory();
    }

    public ApiClient(String base, byte[] certificate) throws Exception {
        origin=validateServer(base);
        tls=certificate==null ? null : certificateTrust(certificate);
    }
    public String address() { return origin.toString(); }
    public JSONObject object(String path) throws Exception { return (JSONObject)request("GET",path,null); }
    public JSONArray array(String path) throws Exception { return (JSONArray)request("GET",path,null); }
    public JSONObject post(String path, JSONObject data) throws Exception { return (JSONObject)request("POST",path,data); }
    public void login(String username,String password) throws Exception {
        cookies.getCookieStore().removeAll();csrf="";
        JSONObject result=post("/api/login",new JSONObject().put("username",username).put("password",password));
        csrf=result.getString("csrf");
    }
    public void clear() { cookies.getCookieStore().removeAll();csrf=""; }

    private Object request(String method,String path,JSONObject data) throws Exception {
        if (!path.startsWith("/") || path.startsWith("//")) throw new IOException("Invalid API route.");
        URI uri=origin.resolve(path);
        if (!Objects.equals(uri.getHost(),origin.getHost()) || !uri.getScheme().equals(origin.getScheme()) || uri.getPort()!=origin.getPort())
            throw new IOException("The API route must stay on the selected server.");
        HttpsURLConnection connection=(HttpsURLConnection)uri.toURL().openConnection(Proxy.NO_PROXY);
        connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(12000);connection.setReadTimeout(25000);
        if (tls!=null) connection.setSSLSocketFactory(tls);
        connection.setRequestMethod(method);connection.setRequestProperty("Accept","application/json");
        connection.setRequestProperty("Origin",origin.getScheme()+"://"+origin.getRawAuthority());
        synchronized(cookies) {
            for (Map.Entry<String,List<String>> entry:cookies.get(uri,Collections.emptyMap()).entrySet())
                connection.setRequestProperty(entry.getKey(),String.join("; ",entry.getValue()));
        }
        try {
            if (data!=null) {
                connection.setDoOutput(true);connection.setRequestProperty("Content-Type","application/json; charset=utf-8");
                connection.setRequestProperty("X-CSRF-Token",csrf);
                byte[] body=data.toString().getBytes(StandardCharsets.UTF_8);connection.setFixedLengthStreamingMode(body.length);
                try(OutputStream out=connection.getOutputStream()) { out.write(body); }
            }
            int code=connection.getResponseCode();
            synchronized(cookies) { cookies.put(uri,connection.getHeaderFields()); }
            if (code>=300 && code<400) throw new ApiException(code,"Server redirects are not followed. Check the exact HTTPS server address.");
            InputStream stream=code<400 ? connection.getInputStream() : connection.getErrorStream();
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            if (stream!=null) try(InputStream input=stream) {
                byte[] block=new byte[8192];int n;
                while((n=input.read(block))!=-1) { if (bytes.size()+n>8*1024*1024) throw new IOException("Server response too large.");bytes.write(block,0,n); }
            }
            String text=new String(bytes.toByteArray(),StandardCharsets.UTF_8);
            Object result;
            try { result=new JSONTokener(text).nextValue(); }
            catch(JSONException e) { throw new IOException("The server returned an invalid API response."); }
            if (code>=400) {
                String message=result instanceof JSONObject ? ((JSONObject)result).optString("error","Request failed.") : "Request failed.";
                throw new ApiException(code,message.length()>400 ? message.substring(0,400):message);
            }
            if (!(result instanceof JSONObject) && !(result instanceof JSONArray)) throw new IOException("Invalid API response.");
            return result;
        } finally { connection.disconnect(); }
    }
}
