package ru.alphafuture.credit;

import com.fasterxml.jackson.core.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;
import java.io.IOException;
import java.math.BigDecimal;

/** Числа внешнего контракта без неявного преобразования строк, boolean или дробного ранга. */
class RankingNumbers {
    static class Rank extends StdDeserializer<Integer> {
        Rank() {
            super(Integer.class);
        }

        @Override
        public Integer deserialize(JsonParser parser, DeserializationContext context)
                throws IOException {
            if (!parser.hasToken(JsonToken.VALUE_NUMBER_INT))
                return context.reportInputMismatch(
                        Integer.class, "rank must be an integer JSON number");
            return parser.getIntValue();
        }
    }

    static class Similarity extends StdDeserializer<BigDecimal> {
        Similarity() {
            super(BigDecimal.class);
        }

        @Override
        public BigDecimal deserialize(JsonParser parser, DeserializationContext context)
                throws IOException {
            if (!parser.hasToken(JsonToken.VALUE_NUMBER_INT)
                    && !parser.hasToken(JsonToken.VALUE_NUMBER_FLOAT))
                return context.reportInputMismatch(
                        BigDecimal.class, "similarity must be a JSON number");
            return parser.getDecimalValue();
        }
    }

    static class Recommended extends StdDeserializer<Boolean> {
        Recommended() {
            super(Boolean.class);
        }

        @Override
        public Boolean deserialize(JsonParser parser, DeserializationContext context)
                throws IOException {
            if (!parser.hasToken(JsonToken.VALUE_TRUE) && !parser.hasToken(JsonToken.VALUE_FALSE))
                return context.reportInputMismatch(
                        Boolean.class, "isRecommended must be a JSON boolean");
            return parser.getBooleanValue();
        }
    }
}
