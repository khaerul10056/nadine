// This tests to make sure the password update in Edit Profile form works well

var url = 'http://127.0.0.1:8000';

username = casper.cli.get('username');
password = casper.cli.get('password');

casper.on("page.error", function(msg, trace) {
    this.echo("Page Error: " + msg, "ERROR");
});

casper.test.begin('Can update password in member edit page', 9, function suite(test) {
  casper.start(url + '/member/edit/' + username + '/', function() {
    test.assertTitle("Login | Office Nomads", "Login page title is the one expected");
    test.assertExists('form[method="post"]', "login form is found");
    this.fill("form[method='post']", {
      'username': username,
      'password': password
    }, true);
  });

  casper.then(function() {
    this.log('Logging in', 'debug');
    this.evaluate(function() {
      document.getElementById('loginonly-btn').click();
    });
  })

  casper.then(function() {
    test.assertTitle("Edit Profile | Office Nomads", "Edit Profile title is correct");
    test.assertUrlMatch('/member/edit/' + username + '/', "Edit profile url correct");
  });

  casper.then(function() {
    this.evaluate(function() {
      document.getElementById('password-create').value = 'hellocats';
      document.getElementById('password-confirm').value = 'shenanigans';
      document.getElementsByClassName('sub-btn')[0].click();
    });
  });

  casper.then(function() {
    test.assertUrlMatch('/member/edit/' + username + '/', "Still on edit profile since passwords did not match");
  });

  casper.then(function() {
    this.evaluate(function() {
      document.getElementById('password-create').value = ' hellocats';
      document.getElementById('password-confirm').value = 'hellocats';
      document.getElementsByClassName('sub-btn')[0].click();
    });
  });

  casper.then(function() {
    test.assertUrlMatch('/member/edit/' + username + '/', "Still on edit profile since passwords did not match due to extra whitespace in one element");
  });

  casper.then(function() {
    this.evaluate(function() {
      document.getElementById('password-create').value = 'cats';
      document.getElementById('password-confirm').value = 'cats';
      document.getElementsByClassName('sub-btn')[0].click();
    });
  });

  casper.then(function() {
    test.assertUrlMatch('/member/edit/' + username + '/', "Still on edit profile since passwords are less than 8 characters");
  });

  casper.then(function() {
    this.evaluate(function() {
      document.getElementById('password-create').value = 'Hellocats';
      document.getElementById('password-confirm').value = 'hellocats';
      document.getElementsByClassName('sub-btn')[0].click();
    });
  });

  casper.then(function() {
    test.assertUrlMatch('/member/edit/' + username + '/', "Still on edit profile since passwords are not matched by case");
  });

  casper.then(function() {
    this.evaluate(function() {
      document.getElementById('password-create').value = 'hellocats';
      document.getElementById('password-confirm').value = 'hellocats';
      document.getElementsByClassName('sub-btn')[0].click();
    });
  });

  casper.then(function() {
    test.assertUrlMatch('/member/profile/' + username + '/', "Redirect to profile page when password update works.");
  });

  casper.run(function() {
    test.done();
  })
})