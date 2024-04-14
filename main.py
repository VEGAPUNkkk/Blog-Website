from datetime import date
import os
import smtplib
from tokenize import Triple
from flask import Flask, abort, render_template, redirect, request, url_for, flash
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_required, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from markupsafe import _MarkupEscapeHelper
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, null
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
# Import your forms from the forms.py
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm



app = Flask(__name__)

app.config['SECRET_KEY'] = os.urandom(32)
ckeditor = CKEditor(app)
Bootstrap5(app)


# CREATE DATABASE
class Base(DeclarativeBase):
    pass
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("SQLALCHEMY_DATABASE_URI", "sqlite:///posts.db")
db = SQLAlchemy(model_class=Base)
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)

gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)



# Create a User table for all your registered users. 
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id : Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    name : Mapped[str] = mapped_column(String, nullable=False)
    email : Mapped[str] = mapped_column(String, nullable=False)
    password : Mapped[str] = mapped_column(String, nullable=False)
    
    #************Relationships************#
    posts = db.relationship('BlogPost', back_populates='author')
    comments = relationship("Comment", back_populates="comment_author")


# CONFIGUR TABLES
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)

    #************Relationships************#
    author_id = db.Column(Integer, db.ForeignKey("users.id"))
    author = relationship("User", back_populates="posts")

    comments = db.relationship("Comment", back_populates="parent_post")

class Comment(db.Model):
    __tablename__ = "comments"
    id : Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text : Mapped[str] = mapped_column(String, nullable=False)

        #************Relationships************#
    comment_author = relationship("User", back_populates="comments")
    post_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("blog_posts.id"))
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    parent_post = relationship("BlogPost", back_populates="comments")


with app.app_context():
    db.create_all()


@login_manager.user_loader
def loader_user(user_id):
    return User.query.get(user_id)

def admin_only(func):
    def wrapper(*args, **kwargs):
        if current_user.id == 1:
            return func(*args, **kwargs)
        else:
            return abort(code=403)
    wrapper.__name__ = func.__name__
    return wrapper

# Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if request.method == "POST":
        user = db.session.execute(db.select(User).where(User.email == form.email.data)).scalar()
        if user:
            flash("Email already exists in the DB Login Instead")
            return redirect(url_for("login"))
        new_user = User(
            name = form.name.data,
            email = form.email.data,
            password = generate_password_hash(password= form.password.data, method="scrypt", salt_length= 4)
        )
        db.session.add(new_user)
        db.session.commit()
        find_user = db.session.execute(db.select(User).where(User.email == form.email.data)).scalar()
        login_user(find_user, force=True)
        return redirect(url_for("get_all_posts"))
    return render_template("register.html", form=form)


# Retrieve a user from the database based on their email. 
@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if request.method == "GET":
        return render_template("login.html", form=form)
    if request.method == "POST":
        user = db.session.execute(db.select(User).where(User.email == form.email.data)).scalar()
        if user:
            if check_password_hash(password=form.password.data, pwhash=user.password):
                login_user(user, force=True)
                return redirect("/")
            else:
                flash("Wrong Password")
                return redirect(url_for("login", form=form))
    flash("This Email does not exist, please try again")
    return render_template("login.html", form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)


# Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    form = CommentForm()
    requested_post = db.get_or_404(BlogPost, post_id)
    if request.method == "POST":
        if not current_user.is_authenticated:
            flash("You need to login or register first")
            return redirect(url_for("login"))

        comment = Comment(
            text = form.text.data,
            author_id = current_user.id,
            post_id = post_id
        )
        db.session.add(comment)
        db.session.commit()
        return redirect(url_for("show_post", post_id=post_id))
    return render_template("post.html", post=requested_post, form=form, gravatar=gravatar)


# Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            date=date.today().strftime("%B %d, %Y"),
            author_id = current_user.id
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


# Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


# Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        email = request.form.get("email")
        name = request.form.get("name")
        phone = request.form.get("phone")
        message = request.form.get("message")
        print(f"Subject:FLask Blog Contact Form\n\nName:{name}\nContact:{phone}\nMessage:{message}")
        with smtplib.SMTP("smtp.gmail.com") as connection:
            connection.starttls()
            connection.login(user=os.environ.get("GMAIL"), password=os.environ.get("GMAIL_PASSWORD"))
            connection.sendmail(
                from_addr=email,
                to_addrs=os.environ.get("GMAIL"),
                msg=f"Subject:FLask Blog Contact Form\n\nName:{name}\nContact:{phone}\nMessage:{message}"
            )
        return render_template("contact.html", msg_sent=True)
    return render_template("contact.html", msg_sent=False)

# # pqjc dsjw ldet nmpa       #monkeydluffy7038@gmail.com

if __name__ == "__main__":
    app.run(debug=False)
