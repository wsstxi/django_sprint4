from django.shortcuts import render, get_object_or_404, redirect
from blog.models import Post, Category, Comment
from django.utils import timezone
from django.views.generic import UpdateView, ListView, CreateView, DeleteView
from django.contrib.auth.models import User
from django.urls import reverse_lazy
from django.contrib import messages
from .forms import PostForm, CommentForm
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404
from django.http import HttpResponseForbidden, HttpResponseNotFound


class PostCreateView(LoginRequiredMixin, CreateView):
    model = Post
    form_class = PostForm
    template_name = 'blog/create.html'
    success_url = reverse_lazy('blog:index')

    def form_valid(self, form):
        post = form.save(commit=False)
        post.author = self.request.user

        # Устанавливаем дату если не указана
        if not post.pub_date:
            post.pub_date = timezone.now()

        post.save()

        if form.cleaned_data.get('tags') or hasattr(form, 'save_m2m'):
            form.save_m2m()

        messages.success(
            self.request,
            'Пост успешно создан!'
        )

        return super().form_valid(form)

    def get_initial(self):
        """Предзаполняем дату публикации"""
        initial = super().get_initial()
        initial['pub_date'] = timezone.now()
        return initial

    def get_initial(self):
        return {'pub_date': timezone.now().date()}

    def get_success_url(self):
        """Указываем куда перенаправлять после успеха"""
        return reverse_lazy('blog:profile',
                            kwargs={'username': self.request.user.username})


class PostUpdateView(LoginRequiredMixin, UpdateView):
    model = Post
    form_class = PostForm
    template_name = 'blog/create.html'

    def get_object(self, queryset=None):
        post_id = self.kwargs.get('post_id')
        return get_object_or_404(Post, id=post_id)

    def get(self, request, *args, **kwargs):
        """GET запрос - показываем форму всем аутентифицированным"""
        self.object = self.get_object()

        # Проверяем автора только при отправке формы
        if self.object.author != request.user:
            # Если не автор - редирект на пост
            return redirect('blog:post_detail', post_id=self.object.id)

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """POST запрос - проверяем что пользователь автор"""
        self.object = self.get_object()

        if self.object.author != request.user:
            # Если не автор пытается сохранить - редирект на пост
            return redirect('blog:post_detail', post_id=self.object.id)

        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy('blog:post_detail', kwargs={'post_id': self.object.id})


class PostDeleteView(LoginRequiredMixin, DeleteView):
    model = Post
    template_name = 'blog/delete.html'

    def get_object(self, queryset=None):
        post_id = self.kwargs.get('post_id')
        return get_object_or_404(Post, id=post_id)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Если не автор - редирект на пост
        if self.object.author != request.user:
            return redirect('blog:post_detail', post_id=self.object.id)

        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy('blog:index')


class CommentPermissionMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Общий миксин для одинаковой проверки прав"""

    def get_object(self, queryset=None):
        post_id = self.kwargs.get('post_id')
        pk = self.kwargs.get('pk')
        return get_object_or_404(Comment, pk=pk, post_id=post_id)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        # Получаем объект для проверки
        try:
            self.object = self.get_object()
        except Http404:
            return HttpResponseNotFound("Комментарий не найден")

        if self.object.author != request.user:
            return HttpResponseForbidden("У вас нет прав для этого действия")

        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        comment = self.get_object()
        return comment.author == self.request.user

    def get_success_url(self):
        return reverse_lazy('blog:post_detail', kwargs={'post_id': self.object.post.id})


class CommentUpdateView(CommentPermissionMixin, UpdateView):
    model = Comment
    form_class = CommentForm
    template_name = 'blog/comment.html'


class CommentDeleteView(CommentPermissionMixin, DeleteView):
    model = Comment
    template_name = 'blog/comment.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

 
def index(request):
    post_list = Post.objects.select_related(
        'author',
        'location',
        'category'
    ).filter(
        is_published=True, pub_date__lte=timezone.now(),
        category__is_published=True
    ).order_by(
        '-pub_date'
    ).annotate(comment_count=Count('comments'))  # ← АННОТАЦИЯ В КЛАССЕ!

    paginator = Paginator(post_list, 10)

    # Получаем номер страницы из GET-параметра
    page_number = request.GET.get('page')

    try:
        # Получаем объект страницы
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        # Если page не число, показываем первую страницу
        page_obj = paginator.get_page(1)
    except EmptyPage:
        # Если страница пуста, показываем последнюю
        page_obj = paginator.get_page(paginator.num_pages)

    context = {
        'page_obj': page_obj,
        'paginator': paginator,
    }
    return render(request, 'blog/index.html', context)


def post_detail(request, post_id):
    """
    Страница поста. Автор видит все свои посты, остальные - только опубликованные.
    """
    # 1. Находим пост (без фильтров!)
    post = get_object_or_404(
        Post.objects.select_related('author', 'location', 'category'),
        id=post_id
    )

    # 2. Проверяем, является ли пользователь автором
    is_author = request.user.is_authenticated and request.user == post.author

    # 3. Определяем, может ли пользователь видеть пост
    if not is_author:
        # Не-авторы видят только:
        # - опубликованные посты
        # - с опубликованной категорией
        # - с датой публикации <= сейчас
        if (not post.is_published or 
            not post.category.is_published or
            post.pub_date > timezone.now()):
            raise Http404("Пост не найден")

    # 4. Форма и комментарии (только для опубликованных постов)
    form = CommentForm()

    # Комментарии показываем всем, если пост доступен
    comments = post.comments.all().order_by('created_at')

    context = {
        'post': post,
        'form': form,
        'comments': comments,
        'now': timezone.now(),  # для проверки отложенных постов
    }

    return render(request, 'blog/detail.html', context)


def category_posts(request, category_slug):
    category = get_object_or_404(Category, slug=category_slug,
                                 is_published=True)

    post_list = Post.objects.select_related(
        'author',
        'location',
        'category'
    ).filter(
        category=category,
        is_published=True,
        pub_date__lte=timezone.now(),
        category__is_published=True
    ).order_by(
        '-pub_date'
    ).annotate(comment_count=Count('comments'))

    paginator = Paginator(post_list, 10)
    page_number = request.GET.get('page')

    try:
        page_obj = paginator.get_page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)

    # Получаем объект категории для заголовка
    category = Category.objects.get(slug=category_slug)

    context = {
        'page_obj': page_obj,
        'category': category,
    }
    return render(request, 'blog/category.html', context)


class UserProfileView(ListView):
    """Класс для страницы профиля пользователя."""
    template_name = 'blog/profile.html'
    context_object_name = 'page_obj'  
    paginate_by = 10

    def get_queryset(self):
        """
        Возвращает публикации пользователя.
        """
        username = self.kwargs.get('username')
        # Сохраняем пользователя в атрибут для использования в get_context_data
        self.profile_user = get_object_or_404(User, username=username)

        return Post.objects.filter(
            author=self.profile_user
        ).order_by(
            '-created_at'
        ).annotate(comment_count=Count('comments'))

    def get_context_data(self, **kwargs):
        """
        Добавляем пользователя в контекст как 'profile'.
        """
        context = super().get_context_data(**kwargs)
        context['profile'] = self.profile_user
        return context


class EditProfileView(LoginRequiredMixin, UpdateView):
    """ Класс для редактирования профиля пользователя. """
    model = User
    template_name = 'blog/user.html'
    fields = ['first_name', 'last_name', 'username', 'email']
    # success_url будет определен в get_success_url()

    def get_object(self):
        """
        Возвращает текущего пользователя.
        Проверка через LoginRequiredMixin гарантирует аутентификацию.
        """
        return self.request.user

    def get_success_url(self):
        """
        После успешного обновления возвращает на страницу профиля пользователя.
        """
        return reverse_lazy(
            'blog:profile',
            kwargs={'username': self.request.user.username}
        )

    def form_valid(self, form):
        """ Добавляет сообщение об успехе после сохранения."""
        messages.success(
            self.request,
            'Профиль успешно обновлен!'
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        """
        Можно добавить дополнительный контекст, если нужно.
        """
        context = super().get_context_data(**kwargs)
        return context


@login_required
def add_comment(request, post_id):
    """
    Добавление комментария к посту.
    Адрес: posts/<post_id>/comment/
    """
    post = get_object_or_404(Post, id=post_id)

    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.author = request.user
            comment.post = post
            comment.save()

            messages.success(request, 'Ваш комментарий успешно добавлен!')
            return redirect('blog:post_detail', post_id=post_id)
        else:
            messages.error(request, 'Ошибка при добавлении комментария')

    # Если GET запрос или форма невалидна, возвращаем на страницу поста
    return redirect('blog:post_detail', post_id=post_id)
