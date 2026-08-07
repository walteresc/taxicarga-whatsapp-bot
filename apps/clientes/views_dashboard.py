from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import Cliente
from .forms_dashboard import ClienteForm


@login_required
def cliente_lista(request):
    q = request.GET.get('q', '')
    clientes = Cliente.objects.all().order_by('-fecha_creacion')
    if q:
        from django.db.models import Q
        clientes = clientes.filter(
            Q(nombre__icontains=q) | Q(telefono__icontains=q)
        )
    paginator = Paginator(clientes, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'clientes/lista.html',
                  {'clientes': page_obj, 'page_obj': page_obj, 'q': q,
                   'active_section': 'clientes'})


@login_required
def cliente_crear(request):
    form = ClienteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Cliente creado correctamente.')
        return redirect('cliente_lista')
    return render(request, 'clientes/form.html',
                  {'form': form, 'titulo': 'Nuevo Cliente',
                   'active_section': 'clientes'})


@login_required
def cliente_editar(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    form = ClienteForm(request.POST or None, instance=cliente)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Cliente actualizado.')
        return redirect('cliente_lista')
    return render(request, 'clientes/form.html',
                  {'form': form, 'titulo': 'Editar Cliente',
                   'cliente': cliente,
                   'active_section': 'clientes'})


@login_required
def cliente_eliminar(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    if request.method == 'POST':
        cliente.delete()
        messages.success(request, 'Cliente eliminado.')
        return redirect('cliente_lista')
    return render(request, 'clientes/confirmar_eliminar.html',
                  {'cliente': cliente,
                   'active_section': 'clientes'})
