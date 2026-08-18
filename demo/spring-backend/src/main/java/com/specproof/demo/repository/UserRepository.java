package com.specproof.demo.repository;

import com.specproof.demo.entity.User;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByEmail(String email);

    List<User> findAllByOrderByIdAsc();

    boolean existsByEmail(String email);
}
