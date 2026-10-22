package ru.alphafuture.credit.selection;

public final class TaxId {
    private TaxId() {}
    public static boolean valid(String value) {
        if (value == null || !value.matches("(?:[0-9]{10}|[0-9]{12})") || value.chars().allMatch(c -> c=='0')) return false;
        if (value.length()==10) return digit(value,new int[]{2,4,10,3,5,9,4,6,8})==value.charAt(9)-'0';
        return digit(value,new int[]{7,2,4,10,3,5,9,4,6,8})==value.charAt(10)-'0'
            && digit(value,new int[]{3,7,2,4,10,3,5,9,4,6,8})==value.charAt(11)-'0';
    }
    private static int digit(String value,int[] weights) {
        int sum=0;
        for(int i=0;i<weights.length;i++) sum+=(value.charAt(i)-'0')*weights[i];
        return sum%11%10;
    }
}
