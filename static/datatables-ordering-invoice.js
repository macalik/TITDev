$(document).ready(function() {
    $('table.datatables').DataTable({
        "lengthMenu": [[-1, 20, 50, 75, 100], ["All", 20, 50, 75, 100]]
    });
} );