package com.specproof.demo.config;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitMQConfig {

    public static final String EXCHANGE = "specproof.demo.events";
    public static final String QUEUE = "q.demo.email.changed";
    public static final String ROUTING_KEY = "email.changed";

    @Bean
    public DirectExchange demoExchange() {
        return new DirectExchange(EXCHANGE);
    }

    @Bean
    public Queue emailChangedQueue() {
        return new Queue(QUEUE, true);
    }

    @Bean
    public Binding emailChangedBinding() {
        return BindingBuilder.bind(emailChangedQueue())
                .to(demoExchange())
                .with(ROUTING_KEY);
    }

    @Bean
    public Jackson2JsonMessageConverter messageConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    public RabbitTemplate rabbitTemplate(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter converter) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(converter);
        return template;
    }
}
