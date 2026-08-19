package com.specproof.demo.service;

import com.specproof.demo.entity.Product;
import com.specproof.demo.repository.ProductRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * Isolated stock-deduction boundary: each decrement runs in its own
 * REQUIRES_NEW transaction, so a caller's rollback cannot undo an
 * already-committed decrement.
 */
@Service
public class StockDeductionService {

    private final ProductRepository productRepository;

    public StockDeductionService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void decrement(Long productId, Integer quantity) {
        Product product = productRepository.findById(productId)
                .orElseThrow(() -> new RuntimeException(
                        "Product not found: " + productId));
        product.setStock(product.getStock() - quantity);
        productRepository.saveAndFlush(product);
    }
}
