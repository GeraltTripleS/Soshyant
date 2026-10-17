package com.soshyant.expert;

import android.graphics.Typeface;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.style.*;
import java.util.regex.*;

/** A deliberately small native text formatter. Never interprets document HTML. */
final class AnswerText {
    static CharSequence format(String source) {
        SpannableStringBuilder out=new SpannableStringBuilder();
        boolean code=false;
        for(String line:source.split("\n",-1)) {
            if(line.trim().startsWith("```")){code=!code;continue;}
            int start=out.length();
            if(code){out.append(line).append('\n');out.setSpan(new TypefaceSpan("monospace"),start,out.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);continue;}
            boolean heading=line.matches("^#{1,6} .+");
            if(heading)line=line.replaceFirst("^#{1,6} +","");
            line=line.replaceFirst("^\\s*[-*] +","• ");
            Matcher match=Pattern.compile("\\*\\*(.+?)\\*\\*|`([^`]+)`").matcher(line);int offset=0;
            while(match.find()){
                out.append(line.substring(offset,match.start()));int begin=out.length();
                out.append(match.group(1)!=null?match.group(1):match.group(2));
                out.setSpan(match.group(1)!=null?new StyleSpan(Typeface.BOLD):new TypefaceSpan("monospace"),begin,out.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);offset=match.end();
            }
            out.append(line.substring(offset));
            if(heading){out.setSpan(new StyleSpan(Typeface.BOLD),start,out.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);out.setSpan(new RelativeSizeSpan(1.12f),start,out.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);}
            out.append('\n');
        }
        return out;
    }
}
